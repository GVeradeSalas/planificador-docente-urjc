import streamlit as st
import pandas as pd
import re
import unicodedata

st.set_page_config(layout="wide", page_title="Planificador POD")
st.title("Planificador Docente - Análisis de Compatibilidad y Ocupación")

# --- FUNCIONES AUXILIARES Y ESTADO ---
if 'seleccion_asignaturas' not in st.session_state:
    st.session_state['seleccion_asignaturas'] = []
if 'prof_cargado' not in st.session_state:
    st.session_state['prof_cargado'] = "-- Ninguno --"
if 'horas_precargadas' not in st.session_state:
    st.session_state['horas_precargadas'] = {}

def agregar_asignatura(asig_grupo):
    if asig_grupo not in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].append(asig_grupo)

def eliminar_asignatura(asig_grupo):
    if asig_grupo in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].remove(asig_grupo)

def simplificar_nombre(nombre):
    if pd.isna(nombre): return ""
    return unicodedata.normalize('NFD', str(nombre)).encode('ascii', 'ignore').decode('utf-8').lower()

def buscar_fuerza_profesor(nombre_pod, df_fuerza):
    if df_fuerza.empty or 'Nombre' not in df_fuerza.columns: return None
    nombre_pod_clean = simplificar_nombre(nombre_pod)
    partes_pod = nombre_pod_clean.replace(',', ' ').split()
    
    for idx, row in df_fuerza.iterrows():
        nombre_f_clean = simplificar_nombre(row['Nombre'])
        if all(p in nombre_f_clean for p in partes_pod):
            row['Original_Index'] = idx
            return row
    return None

def generar_fechas_fijas(dia_letra, semestre_str):
    mapa_dias = {'L': 0, 'M': 1, 'X': 2, 'J': 3, 'V': 4, 'S': 5, 'D': 6}
    num_dia = mapa_dias.get(dia_letra.strip().upper())
    if num_dia is None: return []
    
    semestre_clean = str(semestre_str).upper()
    if "PRIMER" in semestre_clean: start_date, end_date = "2026-09-10", "2026-12-22"
    elif "SEGUNDO" in semestre_clean: start_date, end_date = "2027-01-27", "2027-05-11"
    else: return [] 
        
    fechas = pd.date_range(start=start_date, end=end_date, freq='D')
    return [f.strftime('%d/%m/%y') for f in fechas[fechas.weekday == num_dia]]

def parse_turno(hora_inicio):
    try: return "Mañana" if int(hora_inicio.split(':')[0]) < 14 else "Tarde"
    except: return "Desconocido"

@st.cache_data
def cargar_fuerza_docente(ruta_archivo):
    try: return pd.read_excel(ruta_archivo, skiprows=1)
    except Exception: return pd.DataFrame()

@st.cache_data
def cargar_y_procesar(ruta_archivo):
    try: df_crudo = pd.read_excel(ruta_archivo, skiprows=1)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

    eventos = []
    patron_con_fechas = r'([LMXJVSD])=>\((.*?)-(.*?)\)\[(.*?)\]'
    patron_fijo = r'([LMXJVSD])(?:=>)?\s*\(\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*\)(?!\[)'
    
    for index, row in df_crudo.dropna(subset=['Horario']).iterrows():
        horario_str = str(row['Horario']).strip()
        if horario_str.lower() in ['solo examen', 'no', 'nan', '']: continue
            
        codigo_raw = str(row.get('Código', '0')).split('.')[0]
        horas_totales = pd.to_numeric(row.get('Horas', 0), errors='coerce')
        if pd.isna(horas_totales): horas_totales = 0
            
        celda_prof = str(row.get('Profesores', '')).strip()
        
        if celda_prof == '' or celda_prof.lower() in ['no', 'nan']:
            lista_profs = [("Ninguno", 0)]
            horas_disponibles = horas_totales
            estado_ocupacion = "Libre al completo"
        else:
            lista_profs = []
            horas_ocupadas = 0
            nombres_desc = []
            
            segmentos = re.split(r',|\by\b', celda_prof, flags=re.IGNORECASE)
            for seg in segmentos:
                if not seg.strip(): continue
                match = re.search(r'([^\(]+)\s*\(\s*(\d+)[^\)]*\)', seg)
                if match:
                    nom = match.group(1).strip()
                    h = int(match.group(2))
                    lista_profs.append((nom, h))
                    horas_ocupadas += h
                    nombres_desc.append(f"{nom} ({h}h)")
                else:
                    nom = seg.strip()
                    lista_profs.append((nom, horas_totales))
                    horas_ocupadas += horas_totales
                    nombres_desc.append(nom)
                    
            horas_disponibles = max(0, horas_totales - horas_ocupadas)
            if not lista_profs:
                lista_profs = [("Ninguno", 0)]
                estado_ocupacion = "Libre al completo"
            elif horas_disponibles == 0:
                estado_ocupacion = f"Ocupada por {', '.join(nombres_desc)}"
            else:
                estado_ocupacion = f"Compartida con {', '.join(nombres_desc)} (Quedan {horas_disponibles}h)"

        semestre_actual = row.get('Semestre', 'Desconocido')
        
        for prof_nombre, prof_horas in lista_profs:
            for match in re.findall(patron_con_fechas, horario_str):
                dia, hora_inicio, hora_fin, fechas_str = match
                turno = parse_turno(hora_inicio.strip())
                for fecha in [f.strip() for f in fechas_str.split(',')]:
                    eventos.append({'Código': codigo_raw, 'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''), 'Titulación': row.get('Titulación', 'Desconocido'), 'Campus': row.get('Campus', 'Desconocido'), 'Semestre': semestre_actual, 'Turno': turno, 'Horas_Totales': horas_totales, 'Horas_Profesor': prof_horas, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': prof_nombre, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': row.get('Grupo', 'Desconocido'), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})

            for match in re.findall(patron_fijo, horario_str):
                dia, hora_inicio, hora_fin = match
                turno = parse_turno(hora_inicio.strip())
                for fecha in generar_fechas_fijas(dia, semestre_actual):
                    eventos.append({'Código': codigo_raw, 'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''), 'Titulación': row.get('Titulación', 'Desconocido'), 'Campus': row.get('Campus', 'Desconocido'), 'Semestre': semestre_actual, 'Turno': turno, 'Horas_Totales': horas_totales, 'Horas_Profesor': prof_horas, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': prof_nombre, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': row.get('Grupo', 'Desconocido'), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})
                
    df_eventos = pd.DataFrame(eventos)
    if not df_eventos.empty: df_eventos['Fecha_Obj'] = pd.to_datetime(df_eventos['Fecha_str'], format='%d/%m/%y', errors='coerce')
    return df_eventos

# --- CARGA ---
df_eventos = cargar_y_procesar("POD_2026-27_11-5-2026.xlsx")
df_fuerza = cargar_fuerza_docente("Fuerza Docente.xlsx")

# --- BARRA LATERAL ---
if st.sidebar.button("🔄 Actualizar Datos del Excel"):
    st.cache_data.clear()
    st.rerun()

if df_eventos is None or df_eventos.empty:
    st.error("⚠️ No se encuentra el archivo 'POD_2026-27_11-5-2026.xlsx' o está vacío.")
else:
    lista_profesores = sorted([p for p in df_eventos['Profesor_Original'].unique() if p != "Ninguno"])
    
    st.sidebar.header("0. 🧑‍🏫 Cargar Perfil (2ª Vuelta)")
    idx_prof = lista_profesores.index(st.session_state['prof_cargado']) + 1 if st.session_state['prof_cargado'] in lista_profesores else 0
    prof_a_cargar = st.sidebar.selectbox("Selecciona tu perfil para cargar tus horas:", ["-- Ninguno --"] + lista_profesores, index=idx_prof)
    
    if prof_a_cargar != st.session_state['prof_cargado']:
        st.session_state['prof_cargado'] = prof_a_cargar
        if prof_a_cargar != "-- Ninguno --":
            df_prof_load = df_eventos[df_eventos['Profesor_Original'] == prof_a_cargar].drop_duplicates(subset=['Código', 'Grupo'])
            df_prof_load['Asig_Grupo'] = "[" + df_prof_load['Código'] + "] " + df_prof_load['Asignatura'] + " (" + df_prof_load['Grupo'].astype(str) + ") | " + df_prof_load['Estado_Ocupacion']
            st.session_state['seleccion_asignaturas'] = df_prof_load['Asig_Grupo'].tolist()
            st.session_state['horas_precargadas'] = {f"{r['Código']}_{r['Grupo']}": int(r['Horas_Profesor']) for _, r in df_prof_load.iterrows()}
        else:
            st.session_state['seleccion_asignaturas'] = []
            st.session_state['horas_precargadas'] = {}
        st.rerun()

    st.sidebar.header("1. 🎯 Filtros Principales")
    lista_campus = list(df_eventos['Campus'].dropna().unique())
    campus_elegidos = st.sidebar.multiselect("Campus:", lista_campus, default=['MOSTOLES'] if 'MOSTOLES' in lista_campus else [])
    df_f1 = df_eventos[df_eventos['Campus'].isin(campus_elegidos)] if campus_elegidos else df_eventos

    semestres_elegidos = st.sidebar.multiselect("Semestre(s):", sorted(list(df_f1['Semestre'].dropna().unique())))
    df_f2 = df_f1[df_f1['Semestre'].isin(semestres_elegidos)] if semestres_elegidos else df_f1

    titulaciones_elegidas = st.sidebar.multiselect("Titulaciones:", sorted(list(df_f2['Titulación'].dropna().unique())))
    df_f3 = df_f2[df_f2['Titulación'].isin(titulaciones_elegidas)] if titulaciones_elegidas else df_f2

    st.sidebar.header("2. ⏱️ Filtros y Disponibilidad")
    turnos_disp = sorted(list(df_f3['Turno'].dropna().unique()))
    turnos_elegidos = st.sidebar.multiselect("Turno (Mañana/Tarde):", turnos_disp, default=turnos_disp)
    df_f4 = df_f3[df_f3['Turno'].isin(turnos_elegidos)] if turnos_elegidos else df_f3

    ocultar_compartidas = st.sidebar.checkbox("Ocultar asignaturas compartidas (ya empezadas)")
    if ocultar_compartidas:
        df_f4 = df_f4[(df_f4['Profesor_Original'] == 'Ninguno') | (df_f4['Profesor_Original'] == st.session_state['prof_cargado'])]

    st.sidebar.header("3. 🚫 Excluir Asignaturas")
    asignaturas_nombres = sorted(list(df_f4['Asignatura'].dropna().unique()))
    evitar_asig = st.sidebar.multiselect("Selecciona nombres a evitar:", asignaturas_nombres)
    if evitar_asig:
        df_f4 = df_f4[~df_f4['Asignatura'].isin(evitar_asig)]

    st.sidebar.header("4. 📋 Seleccionar Asignaturas")
    mask_disp = (df_f4['Horas_Disponibles'] > 0) | (df_f4['Profesor_Original'] == st.session_state['prof_cargado'])
    df_disponibles = df_f4[mask_disp].copy()
    
    df_disponibles['Asig_Grupo'] = "[" + df_disponibles['Código'] + "] " + df_disponibles['Asignatura'] + " (" + df_disponibles['Grupo'].astype(str) + ") | " + df_disponibles['Estado_Ocupacion']
    lista_opciones = sorted(list(df_disponibles.drop_duplicates(subset=['Código', 'Grupo'])['Asig_Grupo'].dropna().unique()))
    
    st.session_state['seleccion_asignaturas'] = [x for x in st.session_state['seleccion_asignaturas'] if x in lista_opciones]
    asignaturas_elegidas = st.sidebar.multiselect("Elige los grupos:", lista_opciones, key='seleccion_asignaturas')

    paleta = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#FCE4EC", "#F3E5F5", "#E0F2F1", "#FFF8E1", "#FBE9E7", "#ECEFF1"]

    if asignaturas_elegidas:
        df_seleccion = df_disponibles[df_disponibles['Asig_Grupo'].isin(asignaturas_elegidas)].copy()
        df_unicos = df_seleccion.drop_duplicates(subset=['Código', 'Grupo'])
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Ajuste de Horas a Impartir")
        
        horas_asumidas_dict = {}
        for _, r in df_unicos.iterrows():
            max_h_disp = int(r['Horas_Disponibles'])
            clave_id = f"{r['Código']}_{r['Grupo']}"
            h_actual = st.session_state.get('horas_precargadas', {}).get(clave_id, 0)
            
            max_slider = max_h_disp + h_actual
            default_val = h_actual if h_actual > 0 else max_slider
            
            horas_asumidas_dict[clave_id] = st.sidebar.slider(f"[{r['Código']}] {r['Asignatura']} ({r['Grupo']})", 0, max_slider, default_val, 1, key=f"sl_{clave_id}")
            
        horas_totales_asumidas = sum(horas_asumidas_dict.values())
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Progreso Docente (POD)")
        objetivo_horas = st.sidebar.number_input("🎯 Tu objetivo de horas:", 1, 240, 240, 10)
        progreso = min(horas_totales_asumidas / objetivo_horas, 1.0)
        st.sidebar.progress(progreso)
        st.sidebar.metric(label="⏱️ Horas Docentes Asumidas", value=f"{horas_totales_asumidas} h")
        
        horas_faltantes = objetivo_horas - horas_totales_asumidas

        if horas_faltantes > 0:
            st.sidebar.caption(f"Te faltan **{horas_faltantes} h** para completar tu POD ({int(progreso*100)}%).")
            st.sidebar.markdown("---")
            st.sidebar.subheader("💡 Sugerencias Inteligentes")
            
            grupos_sel = df_seleccion['Asig_Grupo'].unique()
            campus_sel = df_seleccion['Campus'].unique()
            nombres_sel = df_seleccion['Asignatura'].unique()
            
            busy_dict = {}
            for _, r in df_seleccion.iterrows():
                if r['Fecha_str'] not in busy_dict: busy_dict[r['Fecha_str']] = []
                busy_dict[r['Fecha_str']].append((r['Hora Inicio'], r['Hora Fin']))
            
            df_eval = df_disponibles[~df_disponibles['Asig_Grupo'].isin(grupos_sel)]
            recomendaciones = []
            
            for asig_grupo, df_grupo in df_eval.groupby('Asig_Grupo'):
                horas_disp = int(df_grupo['Horas_Disponibles'].iloc[0])
                if horas_disp <= 0: continue
                
                tiene_solape = False
                for _, r in df_grupo.iterrows():
                    f = r['Fecha_str']
                    if f in busy_dict:
                        hi, hf = r['Hora Inicio'], r['Hora Fin']
                        for (b_hi, b_hf) in busy_dict[f]:
                            if hi < b_hf and b_hi < hf:
                                tiene_solape = True
                                break
                    if tiene_solape: break
                if tiene_solape: continue
                
                score = 0
                campus_g, codigo_g, nombre_g = df_grupo['Campus'].iloc[0], df_grupo['Código'].iloc[0], df_grupo['Asignatura'].iloc[0]
                if campus_g in campus_sel: score += 10
                if nombre_g in nombres_sel: score += 20 
                if horas_disp <= horas_faltantes: score += 5 
                
                recomendaciones.append({'Asig_Grupo': asig_grupo, 'Nombre': nombre_g, 'Codigo': codigo_g, 'Horas': horas_disp, 'Campus': campus_g, 'Score': score})
            
            if recomendaciones:
                recomendaciones.sort(key=lambda x: x['Score'], reverse=True)
                top_3, top_10 = recomendaciones[:3], recomendaciones[3:10]
                st.sidebar.caption("Opciones compatibles listas para añadir:")
                for rec in top_3:
                    st.sidebar.markdown(f"**[{rec['Codigo']}] {rec['Nombre']}**<br>🏫 {rec['Campus']} | ⏱️ {rec['Horas']}h", unsafe_allow_html=True)
                    st.sidebar.button("➕ Añadir a mi POD", key=f"btn_t3_{rec['Asig_Grupo']}", on_click=agregar_asignatura, args=(rec['Asig_Grupo'],))
                    st.sidebar.markdown("---")
                if top_10:
                    with st.sidebar.expander("Ver más sugerencias (Top 10)"):
                        for rec in top_10:
                            st.markdown(f"**[{rec['Codigo']}] {rec['Nombre']}**<br>🏫 {rec['Campus']} | ⏱️ {rec['Horas']}h", unsafe_allow_html=True)
                            st.button("➕ Añadir a mi POD", key=f"btn_t10_{rec['Asig_Grupo']}", on_click=agregar_asignatura, args=(rec['Asig_Grupo'],))
                            st.markdown("---")
            else:
                st.sidebar.warning("No hay asignaturas compatibles con tu horario.")
        else:
            st.sidebar.success("✅ ¡Has alcanzado tu objetivo de horas!")
    else:
        df_seleccion = pd.DataFrame()
        st.sidebar.info("👈 Selecciona asignaturas en el menú lateral.")

    mapa_colores = {codigo: paleta[i % len(paleta)] for i, codigo in enumerate(df_eventos['Código'].unique())}

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["⏰ Horario Semanal", "📅 Calendario", "📊 Análisis de Conflictos", "🧑‍🏫 Revisión de Compañeros", "📈 Estado Global"])
    
    with tab1:
        if not df_seleccion.empty:
            for semestre in sorted(df_seleccion['Semestre'].astype(str).unique()):
                st.markdown(f"#### 📅 {semestre.upper()}")
                df_sem = df_seleccion[df_seleccion['Semestre'] == semestre].copy()
                df_sem['Franja Horaria'] = df_sem['Hora Inicio'] + " - " + df_sem['Hora Fin']
                
                html = "<style>.ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; margin-bottom: 25px; } .ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; } .ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; } .hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; } .card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); } .card-t { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; color: #222; } .card-i { color: #555; }</style><table class='ht'><tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
                
                for franja in sorted(df_sem['Franja Horaria'].unique()):
                    html += f"<tr><td class='hc'>{franja}</td>"
                    for dia in ['L', 'M', 'X', 'J', 'V']:
                        html += "<td>"
                        for _, r in df_sem[(df_sem['Franja Horaria'] == franja) & (df_sem['Día'] == dia)].drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                            bg = mapa_colores.get(r['Código'], "#E3F2FD")
                            h_asum = horas_asumidas_dict.get(f"{r['Código']}_{r['Grupo']}", 0)
                            html += f"<div class='card-min' style='background-color: {bg};'><div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div><div class='card-i'>{r['Grupo']} ({h_asum}h)</div></div>"
                        html += "</td>"
                    html += "</tr>"
                st.markdown(html + "</table>", unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("📋 Leyenda y Gestión de Asignaturas")
            
            for _, r in df_seleccion.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                col1, col2, col3, col4 = st.columns([0.5, 3.5, 4, 1.5])
                with col1: st.markdown(f"<div style='background-color: {mapa_colores.get(r['Código'])}; width: 100%; height: 40px; border-radius: 5px; border: 1px solid #ccc;'></div>", unsafe_allow_html=True)
                with col2: st.markdown(f"**[{r['Código']}] {r['Asignatura']}**<br><span style='color: #666; font-size: 0.9em;'>Grupo: {r['Grupo']} | {r['Semestre']}</span>", unsafe_allow_html=True)
                with col3: st.markdown(f"🎓 {r['Titulación']}<br>🏫 {r['Campus']} | {r['Turno']}", unsafe_allow_html=True)
                with col4: st.button("❌ Quitar", key=f"del_{r['Asig_Grupo']}", on_click=eliminar_asignatura, args=(r['Asig_Grupo'],))
                st.markdown("---")
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab2:
        if not df_seleccion.empty:
            df_seleccion['Lunes_Semana'] = df_seleccion['Fecha_Obj'] - pd.to_timedelta(df_seleccion['Fecha_Obj'].dt.weekday, unit='d')
            semanas_ordenadas = sorted(df_seleccion['Lunes_Semana'].dropna().unique())
            dias_activos = [d for d in ['L', 'M', 'X', 'J', 'V', 'S', 'D'] if d in df_seleccion['Día'].values]
            
            html = "<style>.scroll-crono { max-height: 650px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; } .ht-crono { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; } .ht-crono th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); } .ht-crono td { border: 1px solid #ddd; padding: 4px; vertical-align: top; background-color: #ffffff; } .hc-sem { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; z-index: 11; } .badge-hora { font-weight: bold; color: #111; font-size: 0.85em; margin-bottom: 3px; border-bottom: 1px dotted rgba(0,0,0,0.2); padding-bottom: 2px; }</style><div class='scroll-crono'><table class='ht-crono'><tr><th class='hc-sem'>Semana</th>"
            for d in dias_activos: html += f"<th>{d}</th>"
            html += "</tr>"
            
            for semana in semanas_ordenadas:
                html += f"<tr><td class='hc-sem'>Semana<br>{semana.strftime('%d/%m/%Y')}</td>"
                for dia in dias_activos:
                    html += "<td>"
                    for _, r in df_seleccion[(df_seleccion['Lunes_Semana'] == semana) & (df_seleccion['Día'] == dia)].sort_values('Hora Inicio').iterrows():
                        html += f"<div class='card-min' style='background-color: {mapa_colores.get(r['Código'], '#E3F2FD')};'><div class='badge-hora'>⏱ {r['Hora Inicio']} - {r['Hora Fin']}</div><div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div><div class='card-i'>Grupo: {r['Grupo']}</div></div>"
                    html += "</td>"
                html += "</tr>"
            st.markdown(html + "</table></div>", unsafe_allow_html=True)
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab3:
        st.subheader("Análisis de Solapamientos, Desplazamientos y Normativa")
        if not df_seleccion.empty:
            
            # --- 1. AUDITORÍA DE NORMATIVA (1ª VUELTA) ---
            st.markdown("### 📜 Cumplimiento de Normativa (1ª Vuelta)")
            alertas_normativa = []
            
            familias_evaluadas = {}
            for _, r in df_unicos.iterrows():
                codigo = r['Código']
                grupo_str = str(r['Grupo']).strip()
                h_asum = horas_asumidas_dict.get(f"{codigo}_{grupo_str}", 0)
                
                if h_asum > 0:
                    madre_calc = re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', grupo_str, flags=re.IGNORECASE).strip()
                    clave_familia = f"{codigo}_{madre_calc}"
                    if clave_familia not in familias_evaluadas:
                        familias_evaluadas[clave_familia] = {'codigo': codigo, 'madre': madre_calc, 'asignatura': r['Asignatura']}

            def get_max_h(codigo, grupo):
                match = df_eventos[(df_eventos['Código'] == codigo) & (df_eventos['Grupo'].astype(str).str.strip() == grupo)]
                if not match.empty: return int(match['Horas_Totales'].iloc[0])
                return 0
                
            def is_half(h, H): return H > 0 and (h == H // 2 or h == (H + 1) // 2)
            def is_full(h, H): return H > 0 and h == H

            for clave, info in familias_evaluadas.items():
                codigo = info['codigo']
                madre = info['madre']
                nombre_asig = info['asignatura']
                
                df_asig_full = df_eventos[df_eventos['Código'] == codigo]
                desdobles_disp = []
                for _, r_disp in df_asig_full.drop_duplicates(subset=['Grupo']).iterrows():
                    g_disp = str(r_disp['Grupo']).strip()
                    if g_disp != madre and re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', g_disp, flags=re.IGNORECASE).strip() == madre:
                        desdobles_disp.append(g_disp)
                
                H_T = get_max_h(codigo, madre)
                h_T = horas_asumidas_dict.get(f"{codigo}_{madre}", 0)
                
                P_data = []
                for p in desdobles_disp:
                    Hp = get_max_h(codigo, p)
                    hp = horas_asumidas_dict.get(f"{codigo}_{p}", 0)
                    if Hp > 0 or hp > 0: P_data.append((p, hp, Hp))
                
                num_prac_full = sum(1 for _, hp, Hp in P_data if is_full(hp, Hp))
                num_prac_cero = sum(1 for _, hp, Hp in P_data if hp == 0)
                
                todo_practicas = all(is_full(hp, Hp) for _, hp, Hp in P_data) if P_data else True
                mitad_practicas = all(is_half(hp, Hp) for _, hp, Hp in P_data) if P_data else True
                cero_practicas = all(hp == 0 for _, hp, Hp in P_data) if P_data else True
                
                es_todo = is_full(h_T, H_T) and todo_practicas
                es_mitad = is_half(h_T, H_T) and mitad_practicas
                
                teoria_y_un_desdoble = False
                if is_full(h_T, H_T) and len(P_data) > 0:
                    if num_prac_full == 1 and num_prac_cero == len(P_data) - 1:
                        teoria_y_un_desdoble = True

                es_teoria_oculta = False
                es_resto_teoria_oculta = False
                if H_T in [70, 90]:
                    if h_T == 60 and cero_practicas: es_teoria_oculta = True
                    if h_T == (H_T - 60) and cero_practicas: es_resto_teoria_oculta = True
                
                if H_T in [70, 90] and h_T > 60:
                    err_msg = f"**[{codigo}] {nombre_asig} ({madre})**: Has seleccionado {h_T}h de {H_T}h. Las asignaturas de 70 y 90 horas tienen desdobles implícitos. Lo máximo que puede coger un profesor son 60h (teoría), las {H_T - 60}h restantes deben ser obligatoriamente para un segundo profesor."
                    alertas_normativa.append(err_msg)
                else:
                    if not (es_todo or es_mitad or teoria_y_un_desdoble or es_teoria_oculta or es_resto_teoria_oculta):
                        err_msg = f"**[{codigo}] {nombre_asig} (Familia {madre})**: Selección inválida o desbalanceada. "
                        detalles = []
                        if H_T > 0 or h_T > 0: detalles.append(f"Teoría ({madre}): {h_T}/{H_T}h")
                        else: detalles.append(f"Teoría ({madre}): No disponible")
                        for gp, hp, Hp in P_data: detalles.append(f"Práctica ({gp}): {hp}/{Hp}h")
                        err_msg += " | ".join(detalles) + ". *Opciones válidas: Asignatura completa, Teoría + 1 Desdoble, o Mitad de Teoría + Mitad de todos sus Desdobles. (Asig. 70/90h: Max 60h o el resto).*"
                        alertas_normativa.append(err_msg)
            
            if alertas_normativa:
                st.warning("⚠️ **Avisos de Normativa:**")
                for alerta in alertas_normativa: st.write(f"- {alerta}")
            else:
                st.success("✅ **Normativa de 1ª Vuelta:** Todas las selecciones cumplen con la normativa y los límites de desdobles ocultos.")

            st.markdown("---")

            # --- 2. SOLAPAMIENTOS Y DESPLAZAMIENTOS ---
            st.markdown("### 🏃‍♂️ Cruces y Desplazamientos")
            conflictos, alertas_desplazamiento = [], []
            df_sel_ord = df_seleccion.drop_duplicates(subset=['Código', 'Grupo', 'Fecha_str', 'Hora Inicio']).sort_values(by=['Fecha_Obj', 'Hora Inicio'])
            
            def min_entre_horas(h1, h2):
                try: return (int(h2.split(':')[0])*60 + int(h2.split(':')[1])) - (int(h1.split(':')[0])*60 + int(h1.split(':')[1]))
                except: return 999

            for fecha, grupo_fecha in df_sel_ord.groupby('Fecha_str'):
                if len(grupo_fecha) > 1:
                    clases = grupo_fecha.to_dict('records')
                    for i in range(len(clases)):
                        for j in range(i + 1, len(clases)):
                            inicio1, fin1, inicio2, fin2 = clases[i]['Hora Inicio'], clases[i]['Hora Fin'], clases[j]['Hora Inicio'], clases[j]['Hora Fin']
                            campus1, campus2 = clases[i]['Campus'], clases[j]['Campus']
                            un_id1 = f"[{clases[i]['Código']}] {clases[i]['Asignatura']} ({clases[i]['Grupo']})"
                            un_id2 = f"[{clases[j]['Código']}] {clases[j]['Asignatura']} ({clases[j]['Grupo']})"
                            
                            if inicio1 < fin2 and inicio2 < fin1:
                                conflictos.append(f"**{fecha}:** {un_id1} ({inicio1}-{fin1}) choca con {un_id2} ({inicio2}-{fin2})")
                            elif campus1 != campus2:
                                gap = min_entre_horas(fin1, inicio2)
                                if 0 <= gap < 60:
                                    alertas_desplazamiento.append(f"**{fecha}:** Margen crítico ({gap} min) de {campus1} ({un_id1}, fin {fin1}) ➔ {campus2} ({un_id2}, inicio {inicio2})")

            if conflictos:
                st.error("⚠️ Solapamientos horarios estrictos detectados:")
                for c in conflictos: st.write(f"- {c}")
            else:
                st.success("✅ No hay solapamientos de horario estrictos en el calendario.")
                
            if alertas_desplazamiento:
                st.warning("⚠️ Alertas de desplazamiento entre sedes (menos de 60 min de margen):")
                for a in alertas_desplazamiento: st.write(f"- {a}")
            else:
                st.success("✅ Los tiempos de desplazamiento entre sedes son seguros.")
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab4:
        st.subheader("Buscador y Revisión de Horarios de Compañeros")
        lista_profesores = sorted([p for p in df_eventos['Profesor_Original'].unique() if p != "Ninguno"])
        prof_buscado = st.selectbox("Selecciona un profesor/a para ver su carga docente:", ["-- Seleccionar --"] + lista_profesores)
        
        if prof_buscado != "-- Seleccionar --":
            df_prof = df_eventos[df_eventos['Profesor_Original'] == prof_buscado].copy()
            df_prof_unicos = df_prof.drop_duplicates(subset=['Código', 'Grupo'])
            horas_prof = df_prof_unicos['Horas_Profesor'].sum()
            
            st.markdown("---")
            info_fuerza = buscar_fuerza_profesor(prof_buscado, df_fuerza)
            
            fuerza_real = 240
            descargas = 0
            if info_fuerza is not None:
                fuerza_real = pd.to_numeric(info_fuerza.get('Fuerza', 240), errors='coerce')
                fuerza_real = 240 if pd.isna(fuerza_real) or fuerza_real <= 0 else fuerza_real
                descargas = pd.to_numeric(info_fuerza.get('DescargaTotal', 0), errors='coerce')
                descargas = 0 if pd.isna(descargas) else descargas
            
            porcentaje_exacto = (horas_prof / fuerza_real) * 100 if fuerza_real > 0 else 0
            
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1: 
                st.metric(label="Horas asignadas", value=f"{horas_prof} h")
            with col2: 
                if info_fuerza is not None:
                    st.metric(label="POD Objetivo (Fuerza)", value=f"{fuerza_real} h", delta=f"-{descargas}h reducciones" if descargas != 0 else None, delta_color="off")
                else:
                    st.metric(label="POD Objetivo (Estimado)", value="240 h")
            
            with col3:
                st.write(f"**Progreso del POD: {porcentaje_exacto:.1f}%**")
                progreso_barra = min(horas_prof / fuerza_real, 1.0) if fuerza_real > 0 else 0.0
                st.progress(progreso_barra)
                
                if horas_prof < fuerza_real: 
                    st.warning(f"💡 **Faltan {fuerza_real - horas_prof}h** (Participará en siguientes vueltas).")
                elif horas_prof == fuerza_real: 
                    st.success("✅ **POD completado exactamente al 100%.**")
                else: 
                    st.success(f"🔥 **POD superado por {horas_prof - fuerza_real}h** (Por encima del 100%).")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.markdown("#### 📜 Cumplimiento de la Normativa del Compañero")
            alertas_normativa_prof = []
            
            familias_prof = {}
            for _, r in df_prof_unicos.iterrows():
                codigo = r['Código']
                grupo_str = str(r['Grupo']).strip()
                h_prof = int(r['Horas_Profesor'])
                
                if h_prof > 0:
                    madre_calc = re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', grupo_str, flags=re.IGNORECASE).strip()
                    clave_familia = f"{codigo}_{madre_calc}"
                    if clave_familia not in familias_prof:
                        familias_prof[clave_familia] = {'codigo': codigo, 'madre': madre_calc, 'asignatura': r['Asignatura']}

            def get_max_h_ev(codigo, grupo):
                match = df_eventos[(df_eventos['Código'] == codigo) & (df_eventos['Grupo'].astype(str).str.strip() == grupo)]
                if not match.empty: return int(match['Horas_Totales'].iloc[0])
                return 0
                
            def get_h_prof(codigo, grupo):
                match = df_prof_unicos[(df_prof_unicos['Código'] == codigo) & (df_prof_unicos['Grupo'].astype(str).str.strip() == grupo)]
                if not match.empty: return int(match['Horas_Profesor'].iloc[0])
                return 0

            def is_half_p(h, H): return H > 0 and (h == H // 2 or h == (H + 1) // 2)
            def is_full_p(h, H): return H > 0 and h == H

            for clave, info in familias_prof.items():
                codigo, madre, nombre_asig = info['codigo'], info['madre'], info['asignatura']
                df_asig_ev = df_eventos[df_eventos['Código'] == codigo]
                
                desdobles_disp = []
                for _, r_disp in df_asig_ev.drop_duplicates(subset=['Grupo']).iterrows():
                    g_disp = str(r_disp['Grupo']).strip()
                    if g_disp != madre and re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', g_disp, flags=re.IGNORECASE).strip() == madre:
                        desdobles_disp.append(g_disp)
                        
                H_T = get_max_h_ev(codigo, madre)
                h_T = get_h_prof(codigo, madre)
                
                P_data = []
                for p in desdobles_disp:
                    Hp = get_max_h_ev(codigo, p)
                    hp = get_h_prof(codigo, p)
                    if Hp > 0 or hp > 0: P_data.append((p, hp, Hp))
                
                num_prac_full = sum(1 for _, hp, Hp in P_data if is_full_p(hp, Hp))
                num_prac_cero = sum(1 for _, hp, Hp in P_data if hp == 0)
                
                todo_prac = all(is_full_p(hp, Hp) for _, hp, Hp in P_data) if P_data else True
                mitad_prac = all(is_half_p(hp, Hp) for _, hp, Hp in P_data) if P_data else True
                cero_prac = all(hp == 0 for _, hp, Hp in P_data) if P_data else True
                
                es_todo = is_full_p(h_T, H_T) and todo_prac
                es_mitad = is_half_p(h_T, H_T) and mitad_prac
                
                teoria_y_un_desdoble = False
                if is_full_p(h_T, H_T) and len(P_data) > 0:
                    if num_prac_full == 1 and num_prac_cero == len(P_data) - 1:
                        teoria_y_un_desdoble = True

                es_teoria_oculta = False
                es_resto_teoria_oculta = False
                if H_T in [70, 90]:
                    if h_T == 60 and cero_prac: es_teoria_oculta = True
                    if h_T == (H_T - 60) and cero_prac: es_resto_teoria_oculta = True

                if H_T in [70, 90] and h_T > 60:
                    err_msg = f"**[{codigo}] {nombre_asig} ({madre})**: Tiene {h_T}h de {H_T}h asignadas. Al ser una asignatura de {H_T}h, tiene un desdoble implícito y supera el máximo legal de 60h (teoría) permitido para un solo docente."
                    alertas_normativa_prof.append(err_msg)
                else:
                    if not (es_todo or es_mitad or teoria_y_un_desdoble or es_teoria_oculta or es_resto_teoria_oculta):
                        err_msg = f"**[{codigo}] {nombre_asig} (Familia {madre})**: "
                        detalles = [f"Teoría ({madre}): {h_T}/{H_T}h"]
                        for gp, hp, Hp in P_data: detalles.append(f"Práctica ({gp}): {hp}/{Hp}h")
                        err_msg += " | ".join(detalles)
                        alertas_normativa_prof.append(err_msg)
            
            if alertas_normativa_prof:
                st.warning("⚠️ **Posibles incumplimientos de normativa en el POD de este docente:**")
                for alerta in alertas_normativa_prof: st.write(f"- {alerta}")
            else:
                st.success("✅ **Auditoría OK:** Las elecciones de este docente cuadran perfectamente con las reglas de 1ª vuelta y límites de 60h.")
            
            st.markdown("---")
            
            st.markdown("#### 📅 Cuadrante Semanal del Compañero")
            for semestre in sorted(df_prof['Semestre'].astype(str).unique()):
                st.markdown(f"##### {semestre.upper()}")
                df_sem_prof = df_prof[df_prof['Semestre'] == semestre].copy()
                df_sem_prof['Franja Horaria'] = df_sem_prof['Hora Inicio'] + " - " + df_sem_prof['Hora Fin']
                
                html_prof = "<style>.ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; margin-bottom: 20px;} .ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; } .ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; } .hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; } .card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }</style><table class='ht'><tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
                
                for franja in sorted(df_sem_prof['Franja Horaria'].unique()):
                    html_prof += f"<tr><td class='hc'>{franja}</td>"
                    for dia in ['L', 'M', 'X', 'J', 'V']:
                        html_prof += "<td>"
                        for _, r in df_sem_prof[(df_sem_prof['Franja Horaria'] == franja) & (df_sem_prof['Día'] == dia)].drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                            bg = paleta[abs(hash(r['Código'])) % len(paleta)]
                            html_prof += f"<div class='card-min' style='background-color: {bg};'><div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div><div class='card-i'>{r['Grupo']} ({r['Horas_Profesor']}h)</div></div>"
                        html_prof += "</td>"
                    html_prof += "</tr>"
                st.markdown(html_prof + "</table>", unsafe_allow_html=True)
        else:
            st.info("Utiliza el desplegable para buscar el horario y estado del POD de un compañero.")

    with tab5:
        st.subheader("📈 Estado Global de la Elección de POD")
        
        df_unicos_global = df_eventos.drop_duplicates(subset=['Código', 'Grupo'])
        total_horas_area = df_unicos_global['Horas_Totales'].sum()
        
        df_unicos_prof = df_eventos.drop_duplicates(subset=['Código', 'Grupo', 'Profesor_Original'])
        total_asignadas = df_unicos_prof[df_unicos_prof['Profesor_Original'] != 'Ninguno']['Horas_Profesor'].sum()
        
        balance = total_asignadas - total_horas_area
        signo_balance = "+" if balance > 0 else ""
        
        pct_global = (total_asignadas / total_horas_area) * 100 if total_horas_area > 0 else 0
        
        # Procesamos a los profesores para el segundo balance
        datos_profs = []
        horas_por_prof = df_unicos_prof[df_unicos_prof['Profesor_Original'] != 'Ninguno'].groupby('Profesor_Original')['Horas_Profesor'].sum().to_dict()
        profs_procesados = set()
        
        if not df_fuerza.empty and 'Nombre' in df_fuerza.columns:
            df_fuerza_ordenado = df_fuerza.copy()
            df_fuerza_ordenado['Index_Orig'] = range(len(df_fuerza_ordenado))
            
            for _, row_f in df_fuerza_ordenado.iterrows():
                nom_f = row_f['Nombre']
                if pd.isna(nom_f): continue
                
                fuerza = pd.to_numeric(row_f.get('Fuerza', 240), errors='coerce')
                fuerza = 240 if pd.isna(fuerza) or fuerza <= 0 else fuerza
                
                h_asig = 0
                for nom_pod, h in horas_por_prof.items():
                    partes_pod = simplificar_nombre(nom_pod).replace(',', ' ').split()
                    if all(p in simplificar_nombre(nom_f) for p in partes_pod):
                        h_asig += h
                        profs_procesados.add(nom_pod)
                        
                pct = min(h_asig / fuerza, 1.0) if fuerza > 0 else 0.0
                is_finished = pct >= 1.0 or (fuerza - h_asig) <= 9
                
                datos_profs.append({
                    'Original_Index': row_f['Index_Orig'],
                    'Is_Finished': is_finished,
                    'Profesor': nom_f,
                    'Horas Asignadas': h_asig,
                    'Objetivo (Fuerza)': fuerza,
                    'Progreso %': round((h_asig / fuerza) * 100, 1) if fuerza > 0 else 0.0,
                    'Ratio': pct,
                    'Estado': "" 
                })
        
        for nom_pod, h in horas_por_prof.items():
            if nom_pod not in profs_procesados:
                fuerza = 240 
                pct = min(h / fuerza, 1.0)
                is_finished = h >= fuerza
                datos_profs.append({
                    'Original_Index': 9999, 
                    'Is_Finished': is_finished,
                    'Profesor': f"{nom_pod} (No en Excel Fuerza)",
                    'Horas Asignadas': h,
                    'Objetivo (Fuerza)': fuerza,
                    'Progreso %': round((h / fuerza) * 100, 1),
                    'Ratio': pct,
                    'Estado': ""
                })

        # --- BALANCE ACTIVO ---
        fuerza_activos = sum(p['Objetivo (Fuerza)'] for p in datos_profs if p['Horas Asignadas'] > 0)
        asignadas_activos = sum(p['Horas Asignadas'] for p in datos_profs if p['Horas Asignadas'] > 0)
        balance_activo = asignadas_activos - fuerza_activos
        signo_activo = "+" if balance_activo > 0 else ""

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📚 Asignaturas Área", f"{total_horas_area} h")
        col2.metric("🧑‍🏫 Asignadas", f"{total_asignadas} h")
        col3.metric("⚖️ Balance Área", f"{balance} h", delta=f"{signo_balance}{balance} h respecto a Total Área", delta_color="normal" if balance >= 0 else "inverse")
        col4.metric("⚖️ Balance Activos", f"{balance_activo} h", delta=f"{signo_activo}{balance_activo} h respecto a docentes activos", delta_color="normal" if balance_activo >= 0 else "inverse")
        col5.metric("📊 Progreso Global", f"{pct_global:.1f} %")
        
        st.progress(min(total_asignadas / total_horas_area, 1.0) if total_horas_area > 0 else 0.0)
        
        st.markdown("---")
        st.markdown("#### 🧑‍🏫 Progreso y Turno de Profesores")
        
        if datos_profs:
            hay_profesores_sin_horas = any(p['Horas Asignadas'] == 0 and p['Original_Index'] != 9999 for p in datos_profs)
            
            # Ordenamos estrictamente por el índice original de Fuerza Docente
            sorted_profs = sorted(datos_profs, key=lambda x: x['Original_Index'])
            found_next = False
            
            for p in sorted_profs:
                if p['Is_Finished']:
                    p['Estado'] = "Completado ✅"
                else:
                    if hay_profesores_sin_horas:
                        if p['Horas Asignadas'] == 0:
                            if not found_next:
                                p['Estado'] = "👉 LE TOCA ELEGIR (1ª Vuelta)"
                                found_next = True
                            else:
                                p['Estado'] = "En espera ⏳ (1ª Vuelta)"
                        else:
                            p['Estado'] = "Esperando 2ª Vuelta ⏳"
                    else:
                        if not found_next:
                            p['Estado'] = "👉 LE TOCA ELEGIR (2ª+ Vuelta)"
                            found_next = True
                        else:
                            p['Estado'] = "En espera ⏳"
            
            # Reordenamos visualmente: primero los no terminados, luego los completados
            sorted_profs_display = sorted(sorted_profs, key=lambda x: (x['Is_Finished'], x['Original_Index']))
            
            for p in sorted_profs_display:
                del p['Original_Index']
                del p['Is_Finished']
                
            df_resumen = pd.DataFrame(sorted_profs_display)
            
            st.dataframe(
                df_resumen,
                column_config={
                    "Profesor": st.column_config.TextColumn("Profesor / Investigador", width="large"),
                    "Horas Asignadas": st.column_config.NumberColumn("Horas Asig.", format="%d h"),
                    "Objetivo (Fuerza)": st.column_config.NumberColumn("Fuerza POD", format="%d h"),
                    "Progreso %": st.column_config.NumberColumn("% Completado", format="%.1f %%"),
                    "Ratio": st.column_config.ProgressColumn("Barra de Progreso", format="%.2f", min_value=0, max_value=1.0),
                    "Estado": st.column_config.TextColumn("Estado / Turno")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No hay datos de profesores para mostrar todavía. Empieza a rellenar el Excel para ver el progreso del equipo.")
