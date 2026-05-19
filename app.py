import streamlit as st
import pandas as pd
import re
import unicodedata

st.set_page_config(layout="wide", page_title="Planificador POD")
st.title("Planificador Docente - Análisis de Compatibilidad y Ocupación")

# --- FUNCIONES AUXILIARES Y ESTADO ---
if 'seleccion_asignaturas' not in st.session_state:
    st.session_state['seleccion_asignaturas'] = []

def agregar_asignatura(asig_grupo):
    """Añade una asignatura desde las sugerencias."""
    if asig_grupo not in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].append(asig_grupo)

def eliminar_asignatura(asig_grupo):
    """Elimina una asignatura desde la leyenda interactiva."""
    if asig_grupo in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].remove(asig_grupo)

def simplificar_nombre(nombre):
    if pd.isna(nombre):
        return ""
    n = unicodedata.normalize('NFD', str(nombre)).encode('ascii', 'ignore').decode('utf-8')
    return n.lower()

def buscar_fuerza_profesor(nombre_pod, df_fuerza):
    if df_fuerza.empty or 'Nombre' not in df_fuerza.columns:
        return None
    nombre_pod_clean = simplificar_nombre(nombre_pod)
    partes_pod = nombre_pod_clean.replace(',', ' ').split()
    
    for _, row in df_fuerza.iterrows():
        nombre_f_clean = simplificar_nombre(row['Nombre'])
        match = True
        for p in partes_pod:
            if p not in nombre_f_clean:
                match = False
                break
        if match:
            return row
    return None

def generar_fechas_fijas(dia_letra, semestre_str):
    mapa_dias = {'L': 0, 'M': 1, 'X': 2, 'J': 3, 'V': 4, 'S': 5, 'D': 6}
    num_dia = mapa_dias.get(dia_letra.strip().upper())
    if num_dia is None:
        return []
    
    semestre_clean = str(semestre_str).upper()
    if "PRIMER" in semestre_clean:
        start_date, end_date = "2026-09-10", "2026-12-22"
    elif "SEGUNDO" in semestre_clean:
        start_date, end_date = "2027-01-27", "2027-05-11"
    else:
        return [] 
        
    fechas = pd.date_range(start=start_date, end=end_date, freq='D')
    return [f.strftime('%d/%m/%y') for f in fechas[fechas.weekday == num_dia]]

@st.cache_data
def cargar_fuerza_docente(ruta_archivo):
    try:
        return pd.read_excel(ruta_archivo, skiprows=1)
    except Exception:
        return pd.DataFrame()

@st.cache_data
def cargar_y_procesar(ruta_archivo):
    try:
        df_crudo = pd.read_excel(ruta_archivo, skiprows=1)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return None

    eventos = []
    patron_con_fechas = r'([LMXJVSD])=>\((.*?)-(.*?)\)\[(.*?)\]'
    patron_fijo = r'([LMXJVSD])(?:=>)?\s*\(\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*\)(?!\[)'
    patron_profesor = r'([^\(]+)\s*\((\d+)\)'
    
    for index, row in df_crudo.dropna(subset=['Horario']).iterrows():
        horario_str = str(row['Horario']).strip()
        if horario_str.lower() in ['solo examen', 'no', 'nan', '']:
            continue
            
        codigo_raw = str(row.get('Código', '0')).split('.')[0]
        horas_totales = pd.to_numeric(row.get('Horas', 0), errors='coerce')
        if pd.isna(horas_totales):
            horas_totales = 0
            
        txt_prof = str(row.get('Profesores', '')).strip()
        if txt_prof == '' or txt_prof.lower() in ['no', 'nan']:
            profesor_asignado, horas_profesor, horas_disponibles, estado_ocupacion = "Ninguno", 0, horas_totales, "Libre al completo"
        else:
            match_prof = re.search(patron_profesor, txt_prof)
            if match_prof:
                profesor_asignado = match_prof.group(1).strip()
                horas_profesor = int(match_prof.group(2))
                horas_disponibles = max(0, horas_totales - horas_profesor)
                estado_ocupacion = f"Ocupada por {profesor_asignado}" if horas_disponibles == 0 else f"Compartida con {profesor_asignado} (Quedan {horas_disponibles}h)"
            else:
                profesor_asignado, horas_profesor, horas_disponibles, estado_ocupacion = txt_prof, horas_totales, 0, f"Ocupada por {txt_prof}"

        semestre_actual = row.get('Semestre', 'Desconocido')

        for match in re.findall(patron_con_fechas, horario_str):
            dia, hora_inicio, hora_fin, fechas_str = match
            for fecha in [f.strip() for f in fechas_str.split(',')]:
                eventos.append({'Código': codigo_raw, 'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''), 'Titulación': row.get('Titulación', 'Desconocido'), 'Campus': row.get('Campus', 'Desconocido'), 'Semestre': semestre_actual, 'Horas_Totales': horas_totales, 'Horas_Profesor': horas_profesor, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': profesor_asignado, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': row.get('Grupo', 'Desconocido'), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})

        for match in re.findall(patron_fijo, horario_str):
            dia, hora_inicio, hora_fin = match
            for fecha in generar_fechas_fijas(dia, semestre_actual):
                eventos.append({'Código': codigo_raw, 'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''), 'Titulación': row.get('Titulación', 'Desconocido'), 'Campus': row.get('Campus', 'Desconocido'), 'Semestre': semestre_actual, 'Horas_Totales': horas_totales, 'Horas_Profesor': horas_profesor, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': profesor_asignado, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': row.get('Grupo', 'Desconocido'), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})
                
    df_eventos = pd.DataFrame(eventos)
    if not df_eventos.empty:
        df_eventos['Fecha_Obj'] = pd.to_datetime(df_eventos['Fecha_str'], format='%d/%m/%y', errors='coerce')
    return df_eventos

# --- CARGA ---
df_eventos = cargar_y_procesar("POD_2026-27_11-5-2026.xlsx")
df_fuerza = cargar_fuerza_docente("Fuerza Docente.xlsx")

if df_eventos is None or df_eventos.empty:
    st.error("⚠️ No se encuentra el archivo 'POD_2026-27_11-5-2026.xlsx' o está vacío.")
else:
    st.sidebar.header("1. Filtra por Campus")
    lista_campus = list(df_eventos['Campus'].dropna().unique())
    campus_elegidos = st.sidebar.multiselect("Selecciona Campus (vacío = todos):", lista_campus, default=['MOSTOLES'] if 'MOSTOLES' in lista_campus else [])
    df_f1 = df_eventos[df_eventos['Campus'].isin(campus_elegidos)] if campus_elegidos else df_eventos

    st.sidebar.header("2. Filtra por Semestre")
    lista_semestres = sorted(list(df_f1['Semestre'].dropna().unique()))
    semestres_elegidos = st.sidebar.multiselect("Selecciona semestre(s):", lista_semestres)
    df_f2 = df_f1[df_f1['Semestre'].isin(semestres_elegidos)] if semestres_elegidos else df_f1

    st.sidebar.header("3. Filtra por Titulación")
    lista_titulaciones = sorted(list(df_f2['Titulación'].dropna().unique()))
    titulaciones_elegidas = st.sidebar.multiselect("Selecciona titulaciones (vacío = todas):", lista_titulaciones)
    df_f3 = df_f2[df_f2['Titulación'].isin(titulaciones_elegidas)] if titulaciones_elegidas else df_f2

    st.sidebar.header("4. Selecciona Asignaturas")
    df_disponibles = df_f3[df_f3['Horas_Disponibles'] > 0].copy()
    df_disponibles['Asig_Grupo'] = "[" + df_disponibles['Código'] + "] " + df_disponibles['Asignatura'] + " (" + df_disponibles['Grupo'].astype(str) + ") | " + df_disponibles['Estado_Ocupacion']
    lista_opciones = sorted(list(df_disponibles['Asig_Grupo'].dropna().unique()))
    
    st.session_state['seleccion_asignaturas'] = [x for x in st.session_state['seleccion_asignaturas'] if x in lista_opciones]

    asignaturas_elegidas = st.sidebar.multiselect(
        "Elige los grupos con vacantes:", 
        lista_opciones,
        key='seleccion_asignaturas'
    )

    paleta = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#FCE4EC", "#F3E5F5", "#E0F2F1", "#FFF8E1", "#FBE9E7", "#ECEFF1"]

    if asignaturas_elegidas:
        df_seleccion = df_disponibles[df_disponibles['Asig_Grupo'].isin(asignaturas_elegidas)].copy()
        df_unicos = df_seleccion.drop_duplicates(subset=['Código', 'Grupo'])
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Ajuste de Horas a Impartir")
        
        horas_asumidas_dict = {}
        for _, r in df_unicos.iterrows():
            max_h = int(r['Horas_Disponibles'])
            titulo_slider = f"[{r['Código']}] {r['Asignatura']} ({r['Grupo']})"
            clave_id = f"{r['Código']}_{r['Grupo']}"
            
            horas_elegidas = st.sidebar.slider(titulo_slider, min_value=0, max_value=max_h, value=max_h, step=1, key=f"slider_{clave_id}")
            horas_asumidas_dict[clave_id] = horas_elegidas
            
        horas_totales_asumidas = sum(horas_asumidas_dict.values())
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Progreso Docente (POD)")
        objetivo_horas = st.sidebar.number_input("🎯 Tu objetivo de horas:", min_value=1, value=240, step=10)
        
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
                if r['Fecha_str'] not in busy_dict:
                    busy_dict[r['Fecha_str']] = []
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
                campus_g = df_grupo['Campus'].iloc[0]
                codigo_g = df_grupo['Código'].iloc[0]
                nombre_g = df_grupo['Asignatura'].iloc[0]
                
                if campus_g in campus_sel: score += 10
                if nombre_g in nombres_sel: score += 20 
                if horas_disp <= horas_faltantes: score += 5 
                
                recomendaciones.append({
                    'Asig_Grupo': asig_grupo,
                    'Nombre': nombre_g,
                    'Codigo': codigo_g,
                    'Horas': horas_disp,
                    'Campus': campus_g,
                    'Score': score
                })
            
            if recomendaciones:
                recomendaciones.sort(key=lambda x: x['Score'], reverse=True)
                top_3 = recomendaciones[:3]
                top_10 = recomendaciones[3:10]
                
                st.sidebar.caption("Opciones compatibles listas para añadir:")
                for rec in top_3:
                    st.sidebar.markdown(f"**[{rec['Codigo']}] {rec['Nombre']}**<br>🏫 {rec['Campus']} | ⏱️ {rec['Horas']}h libres", unsafe_allow_html=True)
                    st.sidebar.button("➕ Añadir a mi POD", key=f"btn_t3_{rec['Asig_Grupo']}", on_click=agregar_asignatura, args=(rec['Asig_Grupo'],))
                    st.sidebar.markdown("---")
                    
                if top_10:
                    with st.sidebar.expander("Ver más sugerencias (Top 10)"):
                        for rec in top_10:
                            st.markdown(f"**[{rec['Codigo']}] {rec['Nombre']}**<br>🏫 {rec['Campus']} | ⏱️ {rec['Horas']}h libres", unsafe_allow_html=True)
                            st.button("➕ Añadir a mi POD", key=f"btn_t10_{rec['Asig_Grupo']}", on_click=agregar_asignatura, args=(rec['Asig_Grupo'],))
                            st.markdown("---")
            else:
                st.sidebar.warning("No se han encontrado asignaturas compatibles con tu horario actual.")

        else:
            st.sidebar.success("✅ ¡Has alcanzado tu objetivo de horas!")
    else:
        df_seleccion = pd.DataFrame()
        st.sidebar.info("👈 Selecciona asignaturas para iniciar tu planificación.")

    mapa_colores = {codigo: paleta[i % len(paleta)] for i, codigo in enumerate(df_eventos['Código'].unique())}

    tab1, tab2, tab3, tab4 = st.tabs([
        "⏰ Cuadrante Horario Semanal", 
        "📅 Calendario Semana a Semana", 
        "📊 Análisis de Conflictos",
        "🧑‍🏫 Buscador de Compañeros"
    ])
    
    with tab1:
        if not df_seleccion.empty:
            st.subheader("Distribución de Horas por Tramo Semanal")
            
            # Obtenemos los semestres únicos presentes en la selección
            semestres_presentes = sorted(df_seleccion['Semestre'].astype(str).unique())
            
            for semestre in semestres_presentes:
                st.markdown(f"#### 📅 {semestre.upper()}")
                df_sem = df_seleccion[df_seleccion['Semestre'] == semestre].copy()
                
                df_sem['Franja Horaria'] = df_sem['Hora Inicio'] + " - " + df_sem['Hora Fin']
                franjas_ordenadas = sorted(df_sem['Franja Horaria'].unique())
                
                html_cuadrante = "<style>"
                html_cuadrante += ".ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; margin-bottom: 25px; }"
                html_cuadrante += ".ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; }"
                html_cuadrante += ".ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; }"
                html_cuadrante += ".hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; }"
                html_cuadrante += ".card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }"
                html_cuadrante += ".card-t { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; color: #222; }"
                html_cuadrante += ".card-i { color: #555; }"
                html_cuadrante += "</style><table class='ht'>"
                html_cuadrante += "<tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
                
                for franja in franjas_ordenadas:
                    html_cuadrante += f"<tr><td class='hc'>{franja}</td>"
                    for dia in ['L', 'M', 'X', 'J', 'V']:
                        html_cuadrante += "<td>"
                        clases_celda = df_sem[(df_sem['Franja Horaria'] == franja) & (df_sem['Día'] == dia)]
                        for _, r in clases_celda.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                            bg_color = mapa_colores.get(r['Código'], "#E3F2FD")
                            h_asumidas = horas_asumidas_dict.get(f"{r['Código']}_{r['Grupo']}", 0)
                            html_cuadrante += f"<div class='card-min' style='background-color: {bg_color};'>"
                            html_cuadrante += f"<div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div>"
                            html_cuadrante += f"<div class='card-i'>{r['Grupo']} ({h_asumidas}h)</div>"
                            html_cuadrante += "</div>"
                        html_cuadrante += "</td>"
                    html_cuadrante += "</tr>"
                html_cuadrante += "</table>"
                st.markdown(html_cuadrante, unsafe_allow_html=True)
            
            # LEYENDA INTERACTIVA AL FINAL
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("📋 Leyenda y Gestión de Asignaturas")
            st.write("Consulta los detalles de tus asignaturas en el calendario o elimínalas si ya no las quieres:")
            
            for _, r in df_seleccion.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                bg_color = mapa_colores.get(r['Código'], "#E3F2FD")
                col1, col2, col3, col4 = st.columns([0.5, 3.5, 4, 1.5])
                with col1:
                    st.markdown(f"<div style='background-color: {bg_color}; width: 100%; height: 40px; border-radius: 5px; border: 1px solid #ccc;'></div>", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"**[{r['Código']}] {r['Asignatura']}**<br><span style='color: #666; font-size: 0.9em;'>Grupo: {r['Grupo']} | {r['Semestre']}</span>", unsafe_allow_html=True)
                with col3:
                    st.markdown(f"🎓 {r['Titulación']}<br>🏫 {r['Campus']}", unsafe_allow_html=True)
                with col4:
                    st.button("❌ Quitar", key=f"del_{r['Asig_Grupo']}", on_click=eliminar_asignatura, args=(r['Asig_Grupo'],))
                st.markdown("---")
                
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab2:
        if not df_seleccion.empty:
            st.subheader("Seguimiento por Fechas Exactas")
            df_seleccion['Lunes_Semana'] = df_seleccion['Fecha_Obj'] - pd.to_timedelta(df_seleccion['Fecha_Obj'].dt.weekday, unit='d')
            semanas_ordenadas = sorted(df_seleccion['Lunes_Semana'].dropna().unique())
            dias_activos = [d for d in ['L', 'M', 'X', 'J', 'V', 'S', 'D'] if d in df_seleccion['Día'].values]
            
            html_crono = "<style>"
            html_crono += ".scroll-crono { max-height: 650px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; }"
            html_crono += ".ht-crono { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }"
            html_crono += ".ht-crono th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); }"
            html_crono += ".ht-crono td { border: 1px solid #ddd; padding: 4px; vertical-align: top; background-color: #ffffff; }"
            html_crono += ".hc-sem { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; z-index: 11; }"
            html_crono += ".badge-hora { font-weight: bold; color: #111; font-size: 0.85em; margin-bottom: 3px; border-bottom: 1px dotted rgba(0,0,0,0.2); padding-bottom: 2px; }"
            html_crono += "</style><div class='scroll-crono'><table class='ht-crono'><tr><th class='hc-sem'>Semana</th>"
            for d in dias_activos: html_crono += f"<th>{d}</th>"
            html_crono += "</tr>"
            
            for semana in semanas_ordenadas:
                html_crono += f"<tr><td class='hc-sem'>Semana<br>{semana.strftime('%d/%m/%Y')}</td>"
                for dia in dias_activos:
                    html_crono += "<td>"
                    clases_celda = df_seleccion[(df_seleccion['Lunes_Semana'] == semana) & (df_seleccion['Día'] == dia)].sort_values('Hora Inicio')
                    for _, r in clases_celda.iterrows():
                        bg_color = mapa_colores.get(r['Código'], "#E3F2FD")
                        html_crono += f"<div class='card-min' style='background-color: {bg_color};'>"
                        html_crono += f"<div class='badge-hora'>⏱ {r['Hora Inicio']} - {r['Hora Fin']}</div>"
                        html_crono += f"<div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div>"
                        html_crono += f"<div class='card-i'>Grupo: {r['Grupo']}</div>"
                        html_crono += "</div>"
                    html_crono += "</td>"
                html_crono += "</tr>"
            html_crono += "</table></div>"
            st.markdown(html_crono, unsafe_allow_html=True)
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab3:
        st.subheader("Análisis de Solapamientos y Desplazamientos")
        if not df_seleccion.empty:
            conflictos = []
            alertas_desplazamiento = []
            df_seleccion_ordenada = df_seleccion.sort_values(by=['Fecha_Obj', 'Hora Inicio'])
            
            def min_entre_horas(h1, h2):
                try:
                    min1 = int(h1.split(':')[0])*60 + int(h1.split(':')[1])
                    min2 = int(h2.split(':')[0])*60 + int(h2.split(':')[1])
                    return min2 - min1
                except:
                    return 999

            for fecha, grupo_fecha in df_seleccion_ordenada.groupby('Fecha_str'):
                if len(grupo_fecha) > 1:
                    clases = grupo_fecha.to_dict('records')
                    for i in range(len(clases)):
                        for j in range(i + 1, len(clases)):
                            inicio1, fin1 = clases[i]['Hora Inicio'], clases[i]['Hora Fin']
                            inicio2, fin2 = clases[j]['Hora Inicio'], clases[j]['Hora Fin']
                            campus1, campus2 = clases[i]['Campus'], clases[j]['Campus']
                            
                            un_id1 = f"[{clases[i]['Código']}] {clases[i]['Asignatura']} ({clases[i]['Grupo']})"
                            un_id2 = f"[{clases[j]['Código']}] {clases[j]['Asignatura']} ({clases[j]['Grupo']})"
                            
                            if inicio1 < fin2 and inicio2 < fin1:
                                conflictos.append({'Fecha': fecha, 'Conflicto': f"{un_id1} ({inicio1}-{fin1}) choca con {un_id2} ({inicio2}-{fin2})"})
                            elif campus1 != campus2:
                                gap = min_entre_horas(fin1, inicio2)
                                if 0 <= gap < 60:
                                    alertas_desplazamiento.append({'Fecha': fecha, 'Alerta': f"Margen crítico ({gap} min) para cambiar de campus: {campus1} ({un_id1}, fin {fin1}) ➔ {campus2} ({un_id2}, inicio {inicio2})"})

            if conflictos:
                st.error("⚠️ Solapamientos horarios estrictos detectados:")
                for c in conflictos: st.write(f"**{c['Fecha']}:** {c['Conflicto']}")
            else:
                st.success("✅ No hay solapamientos de horario estrictos en el calendario.")
                
            if alertas_desplazamiento:
                st.warning("⚠️ Alertas de desplazamiento entre sedes (menos de 60 min de margen de viaje):")
                for a in alertas_desplazamiento: st.write(f"**{a['Fecha']}:** {a['Alerta']}")
            else:
                st.success("✅ Los tiempos de desplazamiento entre sedes son seguros.")
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab4:
        st.subheader("Buscador de Horarios de Compañeros")
        lista_profesores = sorted([p for p in df_eventos['Profesor_Original'].unique() if p != "Ninguno"])
        prof_buscado = st.selectbox("Selecciona un profesor/a para ver su carga docente:", ["-- Seleccionar --"] + lista_profesores)
        
        if prof_buscado != "-- Seleccionar --":
            df_prof = df_eventos[df_eventos['Profesor_Original'] == prof_buscado].copy()
            horas_prof = df_prof.drop_duplicates(subset=['Código', 'Grupo'])['Horas_Profesor'].sum()
            
            st.markdown("---")
            info_fuerza = buscar_fuerza_profesor(prof_buscado, df_fuerza)
            
            if info_fuerza is not None:
                fuerza_real = pd.to_numeric(info_fuerza.get('Fuerza', 240), errors='coerce')
                fuerza_real = 240 if pd.isna(fuerza_real) else fuerza_real
                descargas = pd.to_numeric(info_fuerza.get('DescargaTotal', 0), errors='coerce')
                descargas = 0 if pd.isna(descargas) else descargas
                
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1: st.metric(label="Horas asignadas", value=f"{horas_prof} h")
                with col2: st.metric(label="POD Objetivo (Fuerza)", value=f"{fuerza_real} h", delta=f"-{descargas}h reducciones" if descargas != 0 else None, delta_color="off")
                with col3:
                    if horas_prof < fuerza_real: st.warning(f"💡 **Posible participación en 2ª vuelta.** Le faltan {fuerza_real - horas_prof}h.")
                    else: st.success("✅ **POD completo o superado.** POD cubierto al 100%.")
            else:
                col1, col2 = st.columns([1, 2])
                with col1: st.metric(label="Horas asignadas", value=f"{horas_prof} h")
                with col2:
                    if horas_prof < 240: st.warning(f"💡 **Fuerza teórica (240h).** Le faltarían {240 - horas_prof}h para completar.")
                    else: st.success("✅ **POD aparentemente completo (>240h).**")
            
            st.markdown("#### Cuadrante Semanal")
            
            semestres_prof = sorted(df_prof['Semestre'].astype(str).unique())
            if semestres_prof:
                for semestre in semestres_prof:
                    st.markdown(f"##### 📅 {semestre.upper()}")
                    df_sem_prof = df_prof[df_prof['Semestre'] == semestre].copy()
                    
                    df_sem_prof['Franja Horaria'] = df_sem_prof['Hora Inicio'] + " - " + df_sem_prof['Hora Fin']
                    franjas_prof = sorted(df_sem_prof['Franja Horaria'].unique())
                    
                    html_prof = "<style>.ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; margin-bottom: 20px;} .ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; } .ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; } .hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; } .card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }</style><table class='ht'><tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
                    
                    for franja in franjas_prof:
                        html_prof += f"<tr><td class='hc'>{franja}</td>"
                        for dia in ['L', 'M', 'X', 'J', 'V']:
                            html_prof += "<td>"
                            for _, r in df_sem_prof[(df_sem_prof['Franja Horaria'] == franja) & (df_sem_prof['Día'] == dia)].drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                                bg_color = paleta[abs(hash(r['Código'])) % len(paleta)]
                                html_prof += f"<div class='card-min' style='background-color: {bg_color};'><div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div><div class='card-i'>{r['Grupo']} ({r['Horas_Profesor']}h)</div></div>"
                            html_prof += "</td>"
                        html_prof += "</tr>"
                    html_prof += "</table>"
                    st.markdown(html_prof, unsafe_allow_html=True)
            else:
                st.info("No hay clases registradas en el POD para este docente.")
        else:
            st.info("Utiliza el desplegable para buscar el horario y estado del POD de un compañero.")
