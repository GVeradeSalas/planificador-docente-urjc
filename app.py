import streamlit as st
import pandas as pd
import re
import unicodedata

st.set_page_config(layout="wide", page_title="Planificador POD")
st.title("Planificador Docente - Análisis de Compatibilidad y Ocupación")

def simplificar_nombre(nombre):
    """Limpia tildes y pasa a minúsculas para facilitar el cruce de nombres entre Excels."""
    if pd.isna(nombre):
        return ""
    n = unicodedata.normalize('NFD', str(nombre)).encode('ascii', 'ignore').decode('utf-8')
    return n.lower()

def buscar_fuerza_profesor(nombre_pod, df_fuerza):
    """Busca al profesor en el archivo de Fuerza Docente flexibilizando el orden de apellidos/nombre."""
    if df_fuerza.empty or 'Nombre' not in df_fuerza.columns:
        return None
    
    nombre_pod_clean = simplificar_nombre(nombre_pod)
    partes_pod = nombre_pod_clean.replace(',', ' ').split()
    
    for _, row in df_fuerza.iterrows():
        nombre_f_clean = simplificar_nombre(row['Nombre'])
        
        # Comprobamos si todas las palabras clave del nombre en el POD están en el registro de Fuerza Docente
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
        start_date = "2026-09-10"
        end_date = "2026-12-22"
    elif "SEGUNDO" in semestre_clean:
        start_date = "2027-01-27"
        end_date = "2027-05-11"
    else:
        return [] 
        
    fechas = pd.date_range(start=start_date, end=end_date, freq='D')
    fechas_filtradas = fechas[fechas.weekday == num_dia]
    return [f.strftime('%d/%m/%y') for f in fechas_filtradas]

@st.cache_data
def cargar_fuerza_docente(ruta_archivo):
    try:
        df = pd.read_excel(ruta_archivo, skiprows=1)
        return df
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
            profesor_asignado = "Ninguno"
            horas_profesor = 0
            horas_disponibles = horas_totales
            estado_ocupacion = "Libre al completo"
        else:
            match_prof = re.search(patron_profesor, txt_prof)
            if match_prof:
                profesor_asignado = match_prof.group(1).strip()
                horas_profesor = int(match_prof.group(2))
                horas_disponibles = max(0, horas_totales - horas_profesor)
                if horas_disponibles == 0:
                    estado_ocupacion = f"Ocupada por {profesor_asignado}"
                else:
                    estado_ocupacion = f"Compartida con {profesor_asignado} (Quedan {horas_disponibles}h)"
            else:
                profesor_asignado = txt_prof
                horas_profesor = horas_totales
                horas_disponibles = 0
                estado_ocupacion = f"Ocupada por {profesor_asignado}"

        semestre_actual = row.get('Semestre', 'Desconocido')

        matches_fechas = re.findall(patron_con_fechas, horario_str)
        for match in matches_fechas:
            dia, hora_inicio, hora_fin, fechas_str = match
            fechas = [f.strip() for f in fechas_str.split(',')]
            for fecha in fechas:
                eventos.append({
                    'Código': codigo_raw,
                    'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''),
                    'Titulación': row.get('Titulación', 'Desconocido'),
                    'Campus': row.get('Campus', 'Desconocido'),
                    'Semestre': semestre_actual,
                    'Horas_Totales': horas_totales,
                    'Horas_Profesor': horas_profesor,
                    'Horas_Disponibles': horas_disponibles,
                    'Profesor_Original': profesor_asignado,
                    'Estado_Ocupacion': estado_ocupacion,
                    'Grupo': row.get('Grupo', 'Desconocido'),
                    'Día': dia.strip(),
                    'Fecha_str': fecha,
                    'Hora Inicio': hora_inicio.strip(),
                    'Hora Fin': hora_fin.strip()
                })

        matches_fijos = re.findall(patron_fijo, horario_str)
        for match in matches_fijos:
            dia, hora_inicio, hora_fin = match
            fechas_calculadas = generar_fechas_fijas(dia, semestre_actual)
            for fecha in fechas_calculadas:
                eventos.append({
                    'Código': codigo_raw,
                    'Asignatura': str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', ''),
                    'Titulación': row.get('Titulación', 'Desconocido'),
                    'Campus': row.get('Campus', 'Desconocido'),
                    'Semestre': semestre_actual,
                    'Horas_Totales': horas_totales,
                    'Horas_Profesor': horas_profesor,
                    'Horas_Disponibles': horas_disponibles,
                    'Profesor_Original': profesor_asignado,
                    'Estado_Ocupacion': estado_ocupacion,
                    'Grupo': row.get('Grupo', 'Desconocido'),
                    'Día': dia.strip(),
                    'Fecha_str': fecha,
                    'Hora Inicio': hora_inicio.strip(),
                    'Hora Fin': hora_fin.strip()
                })
                
    df_eventos = pd.DataFrame(eventos)
    if not df_eventos.empty:
        df_eventos['Fecha_Obj'] = pd.to_datetime(df_eventos['Fecha_str'], format='%d/%m/%y', errors='coerce')
    
    return df_eventos

# --- CARGA DE DATOS ---
df_eventos = cargar_y_procesar("POD_2026-27_11-5-2026.xlsx")
df_fuerza = cargar_fuerza_docente("Fuerza Docente.xlsx")

if df_eventos is None or df_eventos.empty:
    st.error("⚠️ No se encuentra el archivo 'POD_2026-27_11-5-2026.xlsx' o está vacío.")
else:
    st.sidebar.header("1. Filtra por Campus")
    lista_campus = list(df_eventos['Campus'].dropna().unique())
    campus_defecto = ['MOSTOLES'] if 'MOSTOLES' in lista_campus else []
    campus_elegidos = st.sidebar.multiselect("Selecciona Campus (vacío = todos):", lista_campus, default=campus_defecto)
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
    
    df_disponibles['Asig_Grupo'] = (
        "[" + df_disponibles['Código'] + "] " + 
        df_disponibles['Asignatura'] + " (" + 
        df_disponibles['Grupo'].astype(str) + ") | " + 
        df_disponibles['Estado_Ocupacion']
    )
    lista_opciones = sorted(list(df_disponibles['Asig_Grupo'].dropna().unique()))
    asignaturas_elegidas = st.sidebar.multiselect("Elige los grupos con vacantes:", lista_opciones)

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
            clave_unica = f"slider_{r['Código']}_{r['Grupo']}"
            
            horas_elegidas = st.sidebar.slider(
                titulo_slider, min_value=0, max_value=max_h, value=max_h, step=1, key=clave_unica
            )
            horas_asumidas_dict[r['Asig_Grupo']] = horas_elegidas
            
        horas_totales_asumidas = sum(horas_asumidas_dict.values())
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Progreso Docente (POD)")
        objetivo_horas = st.sidebar.number_input("🎯 Tu objetivo de horas:", min_value=1, value=240, step=10)
        
        progreso = min(horas_totales_asumidas / objetivo_horas, 1.0)
        st.sidebar.progress(progreso)
        st.sidebar.metric(label="⏱️ Horas Docentes Asumidas", value=f"{horas_totales_asumidas} h")
        
        if horas_totales_asumidas < objetivo_horas:
            st.sidebar.caption(f"Te faltan **{objetivo_horas - horas_totales_asumidas} h** para completar tu POD ({int(progreso*100)}%).")
        else:
            st.sidebar.success("✅ ¡Has alcanzado o superado tu objetivo de horas!")
            
    else:
        df_seleccion = pd.DataFrame()
        st.sidebar.info("👈 Selecciona asignaturas para iniciar tu planificación.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "⏰ Cuadrante Semanal", 
        "📅 Calendario Completo", 
        "📊 Conflictos",
        "🧑‍🏫 Buscador de Compañeros"
    ])
    
    with tab1:
        if not df_seleccion.empty:
            df_seleccion['Franja Horaria'] = df_seleccion['Hora Inicio'] + " - " + df_seleccion['Hora Fin']
            franjas_ordenadas = sorted(df_seleccion['Franja Horaria'].unique())
            dias_semana = ['L', 'M', 'X', 'J', 'V']
            
            codigos_unicos = df_seleccion['Código'].unique()
            mapa_colores = {codigo: paleta[i % len(paleta)] for i, codigo in enumerate(codigos_unicos)}
            
            html_cuadrante = "<style>"
            html_cuadrante += ".ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }"
            html_cuadrante += ".ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; }"
            html_cuadrante += ".ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; }"
            html_cuadrante += ".hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; }"
            html_cuadrante += ".card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }"
            html_cuadrante += ".card-t { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; color: #222; }"
            html_cuadrante += ".card-i { color: #555; }"
            html_cuadrante += "</style>"
            html_cuadrante += "<table class='ht'>"
            html_cuadrante += "<tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
            
            for franja in franjas_ordenadas:
                html_cuadrante += f"<tr><td class='hc'>{franja}</td>"
                for dia in dias_semana:
                    html_cuadrante += "<td>"
                    clases_celda = df_seleccion[(df_seleccion['Franja Horaria'] == franja) & (df_seleccion['Día'] == dia)]
                    clases_unicas_celda = clases_celda.drop_duplicates(subset=['Código', 'Grupo'])
                    
                    for _, r in clases_unicas_celda.iterrows():
                        bg_color = mapa_colores[r['Código']]
                        h_asumidas = horas_asumidas_dict.get(r['Asig_Grupo'], r['Horas_Disponibles'])
                        
                        html_cuadrante += f"<div class='card-min' style='background-color: {bg_color};'>"
                        html_cuadrante += f"<div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div>"
                        html_cuadrante += f"<div class='card-i'>{r['Grupo']} ({h_asumidas}h)</div>"
                        html_cuadrante += "</div>"
                    html_cuadrante += "</td>"
                html_cuadrante += "</tr>"
                
            html_cuadrante += "</table>"
            st.markdown(html_cuadrante, unsafe_allow_html=True)
        else:
            st.info("Sin asignaturas seleccionadas.")

    with tab2:
        if not df_seleccion.empty:
            df_seleccion['Lunes_Semana'] = df_seleccion['Fecha_Obj'] - pd.to_timedelta(df_seleccion['Fecha_Obj'].dt.weekday, unit='d')
            semanas_ordenadas = sorted(df_seleccion['Lunes_Semana'].dropna().unique())
            dias_semana_full = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
            dias_activos = [d for d in dias_semana_full if d in df_seleccion['Día'].values]
            
            html_crono = "<style>"
            html_crono += ".scroll-crono { max-height: 650px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; }"
            html_crono += ".ht-crono { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }"
            html_crono += ".ht-crono th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); }"
            html_crono += ".ht-crono td { border: 1px solid #ddd; padding: 4px; vertical-align: top; background-color: #ffffff; }"
            html_crono += ".hc-sem { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; z-index: 11; }"
            html_crono += ".badge-hora { font-weight: bold; color: #111; font-size: 0.85em; margin-bottom: 3px; border-bottom: 1px dotted rgba(0,0,0,0.2); padding-bottom: 2px; }"
            html_crono += "</style>"
            
            html_crono += "<div class='scroll-crono'><table class='ht-crono'>"
            html_crono += "<tr><th class='hc-sem'>Semana</th>"
            for d in dias_activos:
                html_crono += f"<th>{d}</th>"
            html_crono += "</tr>"
            
            for semana in semanas_ordenadas:
                fecha_str = semana.strftime('%d/%m/%Y')
                html_crono += f"<tr><td class='hc-sem'>Semana<br>{fecha_str}</td>"
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
        if not df_seleccion.empty:
            conflictos = []
            df_seleccion_ordenada = df_seleccion.sort_values(by=['Fecha_Obj', 'Hora Inicio'])
            for fecha, grupo_fecha in df_seleccion_ordenada.groupby('Fecha_str'):
                if len(grupo_fecha) > 1:
                    clases = grupo_fecha.to_dict('records')
                    for i in range(len(clases)):
                        for j in range(i + 1, len(clases)):
                            inicio1, fin1 = clases[i]['Hora Inicio'], clases[i]['Hora Fin']
                            inicio2, fin2 = clases[j]['Hora Inicio'], clases[j]['Hora Fin']
                            if inicio1 < fin2 and inicio2 < fin1:
                                conflictos.append({
                                    'Fecha': fecha,
                                    'Conflicto': f"[{clases[i]['Código']}] {clases[i]['Grupo']} ({inicio1}-{fin1}) choca con [{clases[j]['Código']}] {clases[j]['Grupo']} ({inicio2}-{fin2})"
                                })

            if conflictos:
                st.error("⚠️ ¡Atención! Se han detectado solapamientos en las fechas seleccionadas.")
                for c in conflictos:
                    st.write(f"**{c['Fecha']}:** {c['Conflicto']}")
            else:
                st.success("✅ Todas las asignaturas seleccionadas son perfectamente compatibles en las fechas del calendario.")
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
                with col1:
                    st.metric(label=f"Horas asignadas", value=f"{horas_prof} h")
                with col2:
                    etiqueta_delta = f"{descargas}h reducciones" if descargas < 0 else (f"-{descargas}h reducciones" if descargas > 0 else None)
                    st.metric(label=f"POD Objetivo (Fuerza)", value=f"{fuerza_real} h", delta=etiqueta_delta, delta_color="off")
                with col3:
                    if horas_prof < fuerza_real:
                        st.warning(f"💡 **Posible participación en 2ª vuelta.** Le faltan {fuerza_real - horas_prof}h para completar su POD.")
                    else:
                        st.success("✅ **POD completo o superado.** Es poco probable que necesite coger más horas.")
            else:
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.metric(label=f"Horas asignadas", value=f"{horas_prof} h")
                with col2:
                    if horas_prof < 240:
                        st.warning(f"💡 **Fuerza exacta desconocida.** Asumiendo un estándar de 240h, le faltarían {240 - horas_prof}h.")
                    else:
                        st.success("✅ **POD aparentemente completo (>240h).**")
            
            st.markdown("#### Cuadrante Semanal")
            df_prof['Franja Horaria'] = df_prof['Hora Inicio'] + " - " + df_prof['Hora Fin']
            franjas_prof = sorted(df_prof['Franja Horaria'].unique())
            
            html_prof = "<style>"
            html_prof += ".ht { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; }"
            html_prof += ".ht th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; }"
            html_prof += ".ht td { border: 1px solid #ddd; padding: 4px; vertical-align: top; height: 90px; overflow-y: auto; background-color: #ffffff; }"
            html_prof += ".hc { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; }"
            html_prof += ".card-min { padding: 4px; margin-bottom: 4px; border-radius: 4px; font-size: 0.75em; border-left: 4px solid #999; display: flex; flex-direction: column; overflow: hidden; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }"
            html_prof += "</style>"
            html_prof += "<table class='ht'>"
            html_prof += "<tr><th class='hc'>Hora</th><th>Lunes (L)</th><th>Martes (M)</th><th>Miércoles (X)</th><th>Jueves (J)</th><th>Viernes (V)</th></tr>"
            
            if franjas_prof:
                for franja in franjas_prof:
                    html_prof += f"<tr><td class='hc'>{franja}</td>"
                    for dia in ['L', 'M', 'X', 'J', 'V']:
                        html_prof += "<td>"
                        clases_celda = df_prof[(df_prof['Franja Horaria'] == franja) & (df_prof['Día'] == dia)]
                        clases_unicas_celda = clases_celda.drop_duplicates(subset=['Código', 'Grupo'])
                        
                        for _, r in clases_unicas_celda.iterrows():
                            bg_color = paleta[abs(hash(r['Código'])) % len(paleta)]
                            html_prof += f"<div class='card-min' style='background-color: {bg_color};'>"
                            html_prof += f"<div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div>"
                            html_prof += f"<div class='card-i'>{r['Grupo']} ({r['Horas_Profesor']}h)</div>"
                            html_prof += "</div>"
                        html_prof += "</td>"
                    html_prof += "</tr>"
            else:
                html_prof += "<tr><td colspan='6' style='text-align:center; padding:20px; color:#666;'>No hay clases registradas en el POD para este docente.</td></tr>"
                
            html_prof += "</table>"
            st.markdown(html_prof, unsafe_allow_html=True)
        else:
            st.info("Utiliza el desplegable para buscar el horario y estado del POD de un compañero.")
