import streamlit as st
import pandas as pd
import re
import unicodedata
import datetime

st.set_page_config(layout="wide", page_title="Planificador POD")

# --- FUNCIONES AUXILIARES Y ESTADO ---
if 'seleccion_asignaturas' not in st.session_state:
    st.session_state['seleccion_asignaturas'] = []
if 'prof_cargado' not in st.session_state:
    st.session_state['prof_cargado'] = "-- Ninguno --"
if 'horas_precargadas' not in st.session_state:
    st.session_state['horas_precargadas'] = {}
if 'fuerza_objetivo' not in st.session_state:
    st.session_state['fuerza_objetivo'] = 240

def agregar_asignatura(asig_grupo_id):
    if asig_grupo_id not in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].append(asig_grupo_id)

def eliminar_asignatura(asig_grupo_id):
    if asig_grupo_id in st.session_state['seleccion_asignaturas']:
        st.session_state['seleccion_asignaturas'].remove(asig_grupo_id)

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
    prof_cols = [c for c in df_crudo.columns if 'profesor' in str(c).lower()]
    
    for index, row in df_crudo.dropna(subset=['Horario']).iterrows():
        horario_str = str(row['Horario']).strip()
        if horario_str.lower() in ['solo examen', 'no', 'nan', '']: continue
            
        codigo_raw = str(row.get('Código', '0')).split('.')[0]
        horas_totales = pd.to_numeric(row.get('Horas', 0), errors='coerce')
        if pd.isna(horas_totales): horas_totales = 0
            
        lista_profs = []
        horas_ocupadas = 0
        nombres_desc = []
        
        for col in prof_cols:
            celda_prof = str(row.get(col, '')).strip()
            if celda_prof != '' and celda_prof.lower() not in ['no', 'nan']:
                segmentos = re.split(r',|\by\b|\be\b|/|\n', celda_prof, flags=re.IGNORECASE)
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

        semestre_actual = str(row.get('Semestre', 'Desconocido')).strip()
        titulacion_actual = str(row.get('Titulación', 'Desconocido')).strip()
        if titulacion_actual.lower() == 'nan': titulacion_actual = "Desconocido"
        asignatura_actual = str(row.get('Nombre Asignatura', 'Desconocido')).replace('"', '').strip()
        if asignatura_actual.lower() == 'nan': asignatura_actual = "Desconocido"
        campus_actual = str(row.get('Campus', 'Desconocido')).strip()
        if campus_actual.lower() == 'nan': campus_actual = "Desconocido"
        
        for prof_nombre, prof_horas in lista_profs:
            for match in re.findall(patron_con_fechas, horario_str):
                dia, hora_inicio, hora_fin, fechas_str = match
                turno = parse_turno(hora_inicio.strip())
                for fecha in [f.strip() for f in fechas_str.split(',')]:
                    eventos.append({'Código': codigo_raw, 'Asignatura': asignatura_actual, 'Titulación': titulacion_actual, 'Campus': campus_actual, 'Semestre': semestre_actual, 'Turno': turno, 'Horas_Totales': horas_totales, 'Horas_Profesor': prof_horas, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': prof_nombre, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': str(row.get('Grupo', 'Desconocido')), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})

            for match in re.findall(patron_fijo, horario_str):
                dia, hora_inicio, hora_fin = match
                turno = parse_turno(hora_inicio.strip())
                for fecha in generar_fechas_fijas(dia, semestre_actual):
                    eventos.append({'Código': codigo_raw, 'Asignatura': asignatura_actual, 'Titulación': titulacion_actual, 'Campus': campus_actual, 'Semestre': semestre_actual, 'Turno': turno, 'Horas_Totales': horas_totales, 'Horas_Profesor': prof_horas, 'Horas_Disponibles': horas_disponibles, 'Profesor_Original': prof_nombre, 'Estado_Ocupacion': estado_ocupacion, 'Grupo': str(row.get('Grupo', 'Desconocido')), 'Día': dia.strip(), 'Fecha_str': fecha, 'Hora Inicio': hora_inicio.strip(), 'Hora Fin': hora_fin.strip()})
                
    df_eventos = pd.DataFrame(eventos)
    if not df_eventos.empty: df_eventos['Fecha_Obj'] = pd.to_datetime(df_eventos['Fecha_str'], format='%d/%m/%y', errors='coerce')
    return df_eventos

def generar_html_calendario(df_calendario, horas_evaluacion, df_fijas, mapa_colores):
    START_HOUR, END_HOUR = 8, 22
    TOTAL_HOURS = END_HOUR - START_HOUR
    PIXELS_PER_HOUR = 60
    CALENDAR_HEIGHT = TOTAL_HOURS * PIXELS_PER_HOUR

    def time_to_mins(t_str):
        try:
            h, m = map(int, t_str.split(':'))
            return h * 60 + m
        except: return START_HOUR * 60

    dias_semana = ['L', 'M', 'X', 'J', 'V']
    nombres_dias = {'L': 'Lunes', 'M': 'Martes', 'X': 'Miércoles', 'J': 'Jueves', 'V': 'Viernes'}

    lines = []
    lines.append("<style>")
    lines.append(".cal-container { display: flex; width: 100%; border: 1px solid #ddd; background: #fff; font-family: sans-serif; margin-bottom: 25px; border-radius: 5px; overflow: hidden; }")
    lines.append(".cal-yaxis { width: 60px; border-right: 1px solid #ddd; position: relative; background: #fafafa; flex-shrink: 0; }")
    lines.append(".cal-day { flex: 1; border-right: 1px solid #ddd; position: relative; min-width: 120px; }")
    lines.append(".cal-day:last-child { border-right: none; }")
    lines.append(".cal-day-header { text-align: center; font-weight: bold; padding: 8px 0; border-bottom: 1px solid #ddd; background: #f0f2f6; height: 35px; box-sizing: border-box; font-size: 0.85em; color: #31333F; }")
    lines.append(f".cal-grid {{ position: relative; height: {CALENDAR_HEIGHT}px; }}")
    lines.append(".cal-grid-line { position: absolute; width: 100%; border-top: 1px dashed #eee; pointer-events: none; }")
    lines.append(".cal-grid-line-solid { position: absolute; width: 100%; border-top: 1px solid #ddd; pointer-events: none; }")
    lines.append(".cal-time-label { position: absolute; width: 100%; text-align: center; font-size: 0.75em; color: #666; font-weight: bold; transform: translateY(-50%); }")
    lines.append(".cal-event { position: absolute; box-sizing: border-box; padding: 6px; border-radius: 4px; border-left: 4px solid rgba(0,0,0,0.3); overflow: hidden; display: flex; flex-direction: column; font-size: 0.7em; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.1); border-top: 1px solid rgba(0,0,0,0.05); border-right: 1px solid rgba(0,0,0,0.05); border-bottom: 1px solid rgba(0,0,0,0.05); transition: transform 0.1s, z-index 0s; z-index: 10; }")
    lines.append(".cal-event:hover { z-index: 50 !important; transform: scale(1.02); box-shadow: 0 4px 12px rgba(0,0,0,0.3); overflow: visible; height: auto !important; min-height: 100%; }")
    lines.append(".cal-event-time { font-weight: bold; color: #444; margin-bottom: 3px; font-size: 1.1em; }")
    lines.append(".cal-event-title { font-weight: bold; color: #111; margin-bottom: 3px; white-space: normal; font-size: 1.1em; }")
    lines.append(".cal-event-group { color: #333; }")
    lines.append("</style>")
    
    lines.append('<div class="cal-container">')
    lines.append('<div class="cal-yaxis"><div class="cal-day-header" style="border-right: none;">Hora</div><div class="cal-grid">')
    
    for h in range(START_HOUR, END_HOUR + 1):
        top = (h - START_HOUR) * PIXELS_PER_HOUR
        if h % 2 != 0: lines.append(f'<div class="cal-time-label" style="top: {top}px;">{h:02d}:00</div>')
        line_class = "cal-grid-line-solid" if h % 2 != 0 else "cal-grid-line"
        lines.append(f'<div class="{line_class}" style="top: {top}px;"></div>')

    lines.append('</div></div>')

    for dia in dias_semana:
        lines.append('<div class="cal-day">')
        lines.append(f'<div class="cal-day-header">{nombres_dias[dia]}</div><div class="cal-grid">')
        
        for h in range(START_HOUR, END_HOUR + 1):
            top = (h - START_HOUR) * PIXELS_PER_HOUR
            line_class = "cal-grid-line-solid" if h % 2 != 0 else "cal-grid-line"
            lines.append(f'<div class="{line_class}" style="top: {top}px;"></div>')

        evs_dia = df_calendario[df_calendario['Día'] == dia].drop_duplicates(subset=['Código', 'Grupo', 'Hora Inicio']).copy()
        
        if not evs_dia.empty:
            events_list = []
            for _, r in evs_dia.iterrows():
                events_list.append({'start': time_to_mins(r['Hora Inicio']), 'end': time_to_mins(r['Hora Fin']), 'data': r})
            
            events_list.sort(key=lambda x: x['start'])
            clusters = []
            for ev in events_list:
                if not clusters: clusters.append([ev])
                else:
                    last_cluster = clusters[-1]
                    if ev['start'] < max(e['end'] for e in last_cluster): last_cluster.append(ev)
                    else: clusters.append([ev])
            
            for cluster in clusters:
                columns = []
                for ev in cluster:
                    placed = False
                    for col in columns:
                        if col[-1]['end'] <= ev['start']:
                            col.append(ev)
                            placed = True
                            break
                    if not placed: columns.append([ev])
                
                num_cols = len(columns)
                for col_idx, col in enumerate(columns):
                    for ev in col:
                        ev['left'] = (col_idx / num_cols) * 100
                        ev['width'] = (1 / num_cols) * 100

            for ev in events_list:
                r = ev['data']
                start_px = (ev['start'] - START_HOUR * 60) * (PIXELS_PER_HOUR / 60)
                height_px = (ev['end'] - ev['start']) * (PIXELS_PER_HOUR / 60)
                bg_color = mapa_colores.get(r['Código'], "#E3F2FD")
                h_asum = horas_evaluacion.get(f"{r['Código']}_{r['Grupo']}", 0)
                is_inmutable = False
                if df_fijas is not None and not df_fijas.empty:
                    is_inmutable = ((df_fijas['Código'] == r['Código']) & (df_fijas['Grupo'] == r['Grupo'])).any()
                icono = "🔒 " if is_inmutable else "✨ " if df_fijas is not None else ""
                
                lines.append(f'<div class="cal-event" style="top: {start_px}px; height: {height_px}px; left: {ev["left"]}%; width: {ev["width"]}%; background-color: {bg_color};">')
                lines.append(f'<div class="cal-event-time">⏱ {r["Hora Inicio"]} - {r["Hora Fin"]}</div>')
                lines.append(f'<div class="cal-event-title" title="[{r["Código"]}] {r["Asignatura"]}">{icono}[{r["Código"]}] {r["Asignatura"]}</div>')
                lines.append(f'<div class="cal-event-group">Gr. {r["Grupo"]} ({h_asum}h)</div></div>')
        lines.append('</div></div>')
    lines.append('</div>')
    return "".join(lines)

# --- CARGA ---
df_eventos = cargar_y_procesar("POD_2026-27_11-5-2026.xlsx")
df_fuerza = cargar_fuerza_docente("Fuerza Docente.xlsx")

# --- DECLARACIÓN PESTAÑAS (Arquitectura Principal) ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚙️ MI POD: Selección",
    "👤 MI POD: Horario Semanal", 
    "👤 MI POD: Calendario", 
    "👤 MI POD: Conflictos", 
    "👥 GENERAL: Vista individual", 
    "🌐 GENERAL: Estado Global"
])

# --- BARRA LATERAL (Solo Resumen) ---
st.sidebar.title("Panel Docente")
if st.sidebar.button("🔄 Actualizar Datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

if df_eventos is None or df_eventos.empty:
    st.error("⚠️ No se encuentra el archivo 'POD_2026-27_11-5-2026.xlsx' o está vacío.")
    st.stop()

# --- PROCESAMIENTO PESTAÑA 1 (FILTROS Y SELECCIÓN) ---
with tab1:
    st.header("⚙️ Configuración y Selección de POD")
    
    # PERFIL
    df_unicos_prof_calc = df_eventos.drop_duplicates(subset=['Código', 'Grupo', 'Profesor_Original'])
    horas_por_prof_calc = df_unicos_prof_calc[df_unicos_prof_calc['Profesor_Original'] != 'Ninguno'].groupby('Profesor_Original')['Horas_Profesor'].sum().to_dict()
    lista_profesores_activos = []
    for p in df_eventos['Profesor_Original'].unique():
        if p == "Ninguno": continue
        info_f = buscar_fuerza_profesor(p, df_fuerza)
        f_real = pd.to_numeric(info_f.get('Fuerza', 240), errors='coerce') if info_f is not None else 240
        f_real = 240 if pd.isna(f_real) or f_real <= 0 else f_real
        if (f_real - horas_por_prof_calc.get(p, 0)) > -20: lista_profesores_activos.append(p)
    lista_profesores_activos.sort()

    idx_prof = lista_profesores_activos.index(st.session_state['prof_cargado']) + 1 if st.session_state['prof_cargado'] in lista_profesores_activos else 0
    prof_a_cargar = st.selectbox("🧑‍🏫 1. Cargar Perfil (Para 2ª Vuelta)", ["-- Ninguno --"] + lista_profesores_activos, index=idx_prof, help="Carga tus horas fijas e inmutables de la 1ª vuelta.")
    
    if prof_a_cargar != st.session_state['prof_cargado']:
        st.session_state['prof_cargado'] = prof_a_cargar
        st.session_state['seleccion_asignaturas'] = [] 
        if prof_a_cargar != "-- Ninguno --":
            info_fuerza_cargado = buscar_fuerza_profesor(prof_a_cargar, df_fuerza)
            st.session_state['fuerza_objetivo'] = pd.to_numeric(info_fuerza_cargado.get('Fuerza', 240), errors='coerce') if info_fuerza_cargado is not None else 240
        else: st.session_state['fuerza_objetivo'] = 240
        st.rerun()

    df_inmutables = pd.DataFrame()
    horas_inmutables_total = 0
    if st.session_state['prof_cargado'] != "-- Ninguno --":
        df_inmutables = df_eventos[df_eventos['Profesor_Original'] == st.session_state['prof_cargado']].copy()
        if not df_inmutables.empty:
            df_inmutables['Es_Inmutable'] = True
            horas_inmutables_total = df_inmutables.drop_duplicates(subset=['Código', 'Grupo'])['Horas_Profesor'].sum()

    st.markdown("---")
    st.markdown("#### 🎯 Filtros de Búsqueda")
    colF1, colF2, colF3 = st.columns(3)
    
    with colF1:
        lista_campus = list(df_eventos['Campus'].dropna().unique())
        campus_elegidos = st.multiselect("Campus:", lista_campus, default=['MOSTOLES'] if 'MOSTOLES' in lista_campus else [])
        df_f1 = df_eventos[df_eventos['Campus'].isin(campus_elegidos)] if campus_elegidos else df_eventos
        
        semestres_elegidos = st.multiselect("Semestre(s):", sorted(list(df_f1['Semestre'].dropna().unique())))
        df_f2 = df_f1[df_f1['Semestre'].isin(semestres_elegidos)] if semestres_elegidos else df_f1

    with colF2:
        titulaciones_elegidas = st.multiselect("Titulaciones:", sorted(list(df_f2['Titulación'].dropna().unique())))
        df_f3 = df_f2[df_f2['Titulación'].isin(titulaciones_elegidas)] if titulaciones_elegidas else df_f2
        
        asignaturas_nombres = sorted(list(df_f3['Asignatura'].dropna().unique()))
        evitar_asig = st.multiselect("🚫 Excluir nombres específicos:", asignaturas_nombres)

    with colF3:
        min_t, max_t = datetime.time(8, 0), datetime.time(22, 0)
        rango_horas = st.slider("Rango horario:", min_value=min_t, max_value=max_t, value=(min_t, max_t), format="HH:mm")
        start_str, end_str = rango_horas[0].strftime("%H:%M"), rango_horas[1].strftime("%H:%M")
        
        st.markdown("<br>", unsafe_allow_html=True)
        ocultar_compartidas = st.checkbox("👁️ Ocultar asignaturas a compartir")
        strict_mode = st.checkbox("🔒 Modo Estricto (Ocultar si hay solape)")

    # Aplicación de filtros
    claves_asignaturas = df_f3['Código'] + "_" + df_f3['Grupo'].astype(str)
    condicion_fuera_rango = (df_f3['Hora Inicio'] < start_str) | (df_f3['Hora Fin'] > end_str)
    claves_fuera = df_f3[condicion_fuera_rango]['Código'] + "_" + df_f3[condicion_fuera_rango]['Grupo'].astype(str)
    df_f4 = df_f3[~claves_asignaturas.isin(claves_fuera.unique())].copy()

    if ocultar_compartidas: df_f4 = df_f4[df_f4['Profesor_Original'] == 'Ninguno']
    if evitar_asig: df_f4 = df_f4[~df_f4['Asignatura'].isin(evitar_asig)]

    # Filtro disponibilidad
    df_disponibles = df_f4[df_f4['Horas_Disponibles'] > 0].copy()
    df_disponibles['Asig_Grupo_ID'] = "[" + df_disponibles['Código'].astype(str) + "] " + df_disponibles['Asignatura'].astype(str) + " (" + df_disponibles['Grupo'].astype(str) + ") - " + df_disponibles['Titulación'].astype(str)
    df_disponibles['Asig_Grupo_Label'] = df_disponibles['Asig_Grupo_ID'] + " | " + df_disponibles['Estado_Ocupacion'].astype(str)
    
    label_dict = df_disponibles.drop_duplicates(subset=['Código', 'Grupo']).set_index('Asig_Grupo_ID')['Asig_Grupo_Label'].to_dict()
    lista_opciones_id = sorted(list(label_dict.keys()))

    # --- CÁLCULO DE ASIGNATURAS COMPLETAMENTE LIBRES (CON FILTROS APLICADOS) ---
    # 1. Función para asociar cualquier línea (Teoría o Desdoble) con su Grupo Madre (AM, BM, AT, BT)
    def obtener_grupo_madre(grupo):
        g_str = str(grupo)
        for m in ["AM", "BM", "AT", "BT"]:
            if m in g_str:
                return m
        return g_str

    # Creamos una columna temporal en el df GLOBAL para saber qué está ocupado realmente
    df_eventos['Grupo_Madre_Analisis'] = df_eventos['Grupo'].apply(obtener_grupo_madre)
    
    # 2. Identificar las combinaciones ocupadas mirando TODO el archivo (Verdad absoluta)
    df_lineas_ocupadas = df_eventos[df_eventos['Profesor_Original'] != 'Ninguno']
    combinaciones_ocupadas = set(zip(df_lineas_ocupadas['Código'], df_lineas_ocupadas['Grupo_Madre_Analisis']))
    
    # 3. Extraer las madres reales SOLO de los datos que cumplen tus filtros actuales
    # ⚠️ IMPORTANTE: Cambia 'df_filtrado' por el nombre de tu variable de datos filtrados
    df_disponibles['Grupo_Madre_Analisis'] = df_disponibles['Grupo'].apply(obtener_grupo_madre)
    df_madres_reales = df_disponibles[df_disponibles['Grupo'].isin(["AM", "BM", "AT", "BT"])].drop_duplicates(subset=['Código', 'Grupo'])
    
    # 4. Filtrar cuáles están 100% libres cruzando lo visible con la verdad absoluta
    lista_desplegable_libres = []
    for _, r in df_madres_reales.iterrows():
        clave_actual = (r['Código'], r['Grupo'])
        if clave_actual not in combinaciones_ocupadas:
            lista_desplegable_libres.append(
                f"[{r['Código']}] {r['Asignatura']} ({r['Grupo']}) - {r['Titulación']} | 🏫 {r['Campus']}"
            )
    
    # 5. Interfaz gráfica
    with st.expander(f"🔍 Ver Asignaturas Completamente Libres (acorde a los filtros) ({len(lista_desplegable_libres)})", expanded=False):
        if lista_desplegable_libres:
            st.write("Las siguientes asignaturas (que cumplen tus filtros actuales) no tienen asignado ningún docente:")
            for asig in lista_desplegable_libres:
                st.markdown(f"• {asig}")
        else:
            st.info("No quedan asignaturas completamente libres que coincidan con los filtros aplicados.")

    # Matriz Solapamientos
    sel_actual = [x for x in st.session_state.get('seleccion_asignaturas', []) if x in lista_opciones_id]
    busy_dict = {}
    conflictos_exist = False
    
    if not df_inmutables.empty:
        for _, r in df_inmutables.iterrows():
            f = r['Fecha_str']
            if f not in busy_dict: busy_dict[f] = []
            busy_dict[f].append((r['Hora Inicio'], r['Hora Fin']))
            
    if sel_actual:
        df_sel_temp = df_disponibles[df_disponibles['Asig_Grupo_ID'].isin(sel_actual)]
        for _, r in df_sel_temp.iterrows():
            f = r['Fecha_str']
            hi, hf = r['Hora Inicio'], r['Hora Fin']
            if f not in busy_dict: busy_dict[f] = []
            for b_hi, b_hf in busy_dict[f]:
                if hi < b_hf and b_hi < hf: conflictos_exist = True
            busy_dict[f].append((hi, hf))

    if strict_mode:
        if conflictos_exist:
            st.session_state['seleccion_asignaturas'] = []
            st.warning("⚠️ Modo estricto activado: Se reinicia la NUEVA elección al detectar solapamientos.")
            st.rerun()
        else:
            valid_options = []
            for ag_id, grp_df in df_disponibles.groupby('Asig_Grupo_ID'):
                if ag_id in sel_actual:
                    valid_options.append(ag_id)
                    continue
                overlap = False
                for _, r in grp_df.iterrows():
                    f = r['Fecha_str']
                    hi, hf = r['Hora Inicio'], r['Hora Fin']
                    if f in busy_dict:
                        for b_hi, b_hf in busy_dict[f]:
                            if hi < b_hf and b_hi < hf: overlap = True; break
                    if overlap: break
                if not overlap: valid_options.append(ag_id)
            lista_opciones_id = [x for x in lista_opciones_id if x in valid_options]

    # Panel Dual
    st.markdown("---")
    st.markdown("#### 📋 Selección de Nuevas Asignaturas")
    
    colL, colR = st.columns(2)
    with colL:
        st.markdown("##### 🛒 Disponibles en el Buscador")
        with st.container(height=500, border=True):
            if not lista_opciones_id: st.info("No hay asignaturas que coincidan con los filtros.")
            for ag_id in lista_opciones_id:
                if ag_id not in sel_actual:
                    c1, c2 = st.columns([5, 1])
                    c1.markdown(f"<span style='font-size:0.85em'>{label_dict[ag_id]}</span>", unsafe_allow_html=True)
                    c2.button("➕", key=f"add_{ag_id}", on_click=agregar_asignatura, args=(ag_id,))
                    st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

    df_seleccion = pd.DataFrame()
    horas_asumidas_dict = {}

    with colR:
        st.markdown("##### ✨ Tu Nueva Selección")
        with st.container(height=500, border=True):
            if not sel_actual: st.info("Aún no has añadido nuevas asignaturas.")
            df_seleccion = df_disponibles[df_disponibles['Asig_Grupo_ID'].isin(sel_actual)].copy()
            df_seleccion['Es_Inmutable'] = False
            
            for ag_id in sel_actual:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"<span style='font-size:0.85em; font-weight:bold;'>{label_dict[ag_id]}</span>", unsafe_allow_html=True)
                c2.button("❌", key=f"rem_{ag_id}", on_click=eliminar_asignatura, args=(ag_id,))
                
                # Sliders
                grp_df = df_seleccion[df_seleccion['Asig_Grupo_ID'] == ag_id].drop_duplicates(subset=['Código', 'Grupo'])
                if not grp_df.empty:
                    r = grp_df.iloc[0]
                    max_h_disp = int(r['Horas_Disponibles'])
                    clave_id = f"{r['Código']}_{r['Grupo']}"
                    horas_asumidas_dict[clave_id] = st.slider(f"Horas: {r['Grupo']}", 0, max_h_disp, max_h_disp, 1, key=f"sl_{clave_id}")
                st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)

    horas_nuevas_total = sum(horas_asumidas_dict.values())
    horas_totales_asumidas = horas_inmutables_total + horas_nuevas_total

    # --- CÁLCULOS NORMATIVA ---
    alertas_normativa = []
    conflictos_lista = []
    alertas_desplazamiento = []
    
    dfs_to_concat = []
    if not df_inmutables.empty: dfs_to_concat.append(df_inmutables)
    if not df_seleccion.empty: dfs_to_concat.append(df_seleccion)
    df_union = pd.concat(dfs_to_concat, ignore_index=True) if dfs_to_concat else pd.DataFrame()

    horas_evaluacion = {}
    if not df_inmutables.empty:
        for _, r in df_inmutables.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
            horas_evaluacion[f"{r['Código']}_{r['Grupo']}"] = horas_evaluacion.get(f"{r['Código']}_{r['Grupo']}", 0) + int(r['Horas_Profesor'])
    for clave_id, h in horas_asumidas_dict.items():
        horas_evaluacion[clave_id] = horas_evaluacion.get(clave_id, 0) + h

    if not df_union.empty:
        familias_evaluadas = {}
        for _, r in df_union.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
            codigo = r['Código']
            grupo_str = str(r['Grupo']).strip()
            h_asum = horas_evaluacion.get(f"{codigo}_{grupo_str}", 0)
            if h_asum > 0:
                madre_calc = re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', grupo_str, flags=re.IGNORECASE).strip()
                clave_familia = f"{codigo}_{madre_calc}"
                if clave_familia not in familias_evaluadas:
                    familias_evaluadas[clave_familia] = {'codigo': codigo, 'madre': madre_calc, 'asignatura': r['Asignatura']}

        def get_max_h(codigo, grupo):
            match = df_eventos[(df_eventos['Código'] == codigo) & (df_eventos['Grupo'].astype(str).str.strip() == grupo)]
            return int(match['Horas_Totales'].iloc[0]) if not match.empty else 0
        def is_half(h, H): return H > 0 and (h == H // 2 or h == (H + 1) // 2)
        def is_full(h, H): return H > 0 and h == H

        for clave, info in familias_evaluadas.items():
            codigo, madre, nombre_asig = info['codigo'], info['madre'], info['asignatura']
            df_asig_full = df_eventos[df_eventos['Código'] == codigo]
            desdobles_disp = []
            for _, r_disp in df_asig_full.drop_duplicates(subset=['Grupo']).iterrows():
                g_disp = str(r_disp['Grupo']).strip()
                if g_disp != madre and re.sub(r'[-_ ]?(?:G\d*)?[-_ ]?P\d+$', '', g_disp, flags=re.IGNORECASE).strip() == madre:
                    desdobles_disp.append(g_disp)
            
            H_T, h_T = get_max_h(codigo, madre), horas_evaluacion.get(f"{codigo}_{madre}", 0)
            P_data = []
            for p in desdobles_disp:
                Hp, hp = get_max_h(codigo, p), horas_evaluacion.get(f"{codigo}_{p}", 0)
                if Hp > 0 or hp > 0: P_data.append((p, hp, Hp))
            
            num_prac_full = sum(1 for _, hp, Hp in P_data if is_full(hp, Hp))
            num_prac_cero = sum(1 for _, hp, Hp in P_data if hp == 0)
            todo_prac = all(is_full(hp, Hp) for _, hp, Hp in P_data) if P_data else True
            mitad_prac = all(is_half(hp, Hp) for _, hp, Hp in P_data) if P_data else True
            cero_prac = all(hp == 0 for _, hp, Hp in P_data) if P_data else True
            
            es_todo = is_full(h_T, H_T) and todo_prac
            es_mitad = is_half(h_T, H_T) and mitad_prac
            
            teoria_y_un_desdoble = False
            if is_full(h_T, H_T) and len(P_data) > 0:
                if num_prac_full == 1 and num_prac_cero == len(P_data) - 1: teoria_y_un_desdoble = True

            es_teoria_oculta = False
            es_resto_teoria_oculta = False
            if H_T in [70, 90]:
                if h_T == 60 and cero_prac: es_teoria_oculta = True
                if h_T == (H_T - 60) and cero_prac: es_resto_teoria_oculta = True
            
            if H_T in [70, 90] and h_T > 60:
                alertas_normativa.append(f"**[{codigo}] {nombre_asig} ({madre})**: Máximo 60h para un docente en asig. de {H_T}h.")
            elif not (es_todo or es_mitad or teoria_y_un_desdoble or es_teoria_oculta or es_resto_teoria_oculta):
                alertas_normativa.append(f"**[{codigo}] {nombre_asig} ({madre})**: Selección desbalanceada.")

        df_sel_ord = df_union.drop_duplicates(subset=['Código', 'Grupo', 'Fecha_str', 'Hora Inicio']).sort_values(by=['Fecha_Obj', 'Hora Inicio'])
        def min_entre_horas(h1, h2):
            try: return (int(h2.split(':')[0])*60 + int(h2.split(':')[1])) - (int(h1.split(':')[0])*60 + int(h1.split(':')[1]))
            except: return 999

        for fecha, grupo_fecha in df_sel_ord.groupby('Fecha_str'):
            if len(grupo_fecha) > 1:
                clases = grupo_fecha.to_dict('records')
                for i in range(len(clases)):
                    for j in range(i + 1, len(clases)):
                        if clases[i]['Hora Inicio'] < clases[j]['Hora Fin'] and clases[j]['Hora Inicio'] < clases[i]['Hora Fin']:
                            conflictos_lista.append(f"**{fecha}:** {clases[i]['Asignatura']} choca con {clases[j]['Asignatura']}")
                        elif clases[i]['Campus'] != clases[j]['Campus']:
                            gap = min_entre_horas(clases[i]['Hora Fin'], clases[j]['Hora Inicio'])
                            if 0 <= gap < 60: alertas_desplazamiento.append(f"**{fecha}:** Margen crítico ({gap} min) {clases[i]['Campus']} ➔ {clases[j]['Campus']}")

    if alertas_normativa or conflictos_lista:
        st.markdown("---")
        st.error("⚠️ **Existen problemas en tu selección actual. Revisa la pestaña de Conflictos.**")

# --- BARRA LATERAL (Solo Resumen y Sugerencias) ---
st.sidebar.subheader("Progreso Docente (POD)")
fuerza_default = st.session_state.get('fuerza_objetivo', 240)
objetivo_horas = st.sidebar.number_input("🎯 Tu objetivo de horas:", 1, 300, int(fuerza_default), 10)
progreso = min(horas_totales_asumidas / objetivo_horas, 1.0) if objetivo_horas > 0 else 0
st.sidebar.progress(progreso)
st.sidebar.metric(label="⏱️ Horas Docentes Asumidas", value=f"{horas_totales_asumidas} h")

horas_faltantes = objetivo_horas - horas_totales_asumidas
if horas_faltantes > 0:
    st.sidebar.caption(f"Te faltan **{horas_faltantes} h** para completar tu POD ({int(progreso*100)}%).")
    if not strict_mode and not df_seleccion.empty:
        st.sidebar.markdown("---")
        st.sidebar.subheader("💡 Sugerencias Rápidas")
        grupos_sel = df_seleccion['Asig_Grupo_ID'].unique()
        df_eval = df_disponibles[~df_disponibles['Asig_Grupo_ID'].isin(grupos_sel)]
        recomendaciones = []
        for ag_id, df_grupo in df_eval.groupby('Asig_Grupo_ID'):
            h_d = int(df_grupo['Horas_Disponibles'].iloc[0])
            if 0 < h_d <= horas_faltantes:
                recomendaciones.append({'ID': ag_id, 'Nombre': df_grupo['Asignatura'].iloc[0], 'Campus': df_grupo['Campus'].iloc[0], 'Horas': h_d})
        
        for rec in recomendaciones[:3]:
            st.sidebar.markdown(f"**{rec['Nombre']}**<br>🏫 {rec['Campus']} | ⏱️ {rec['Horas']}h", unsafe_allow_html=True)
            st.sidebar.button("➕ Añadir", key=f"btn_sug_{rec['ID']}", on_click=agregar_asignatura, args=(rec['ID'],))
            st.sidebar.markdown("---")
else:
    st.sidebar.success("✅ ¡Objetivo alcanzado!")
paleta = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#FCE4EC", "#F3E5F5", "#E0F2F1", "#FFF8E1", "#FBE9E7", "#ECEFF1"]
codigos_unicos = df_seleccion['Código'].unique()
mapa_colores = {codigo: paleta[i % len(paleta)] for i, codigo in enumerate(df_eventos['Código'].unique())}


# --- RESTO DE PESTAÑAS ---
with tab2:
    if conflictos_lista: st.error("⚠️ Tienes solapamientos. Ve a **Conflictos**.")
    if alertas_normativa: st.error("⚠️ Tu selección incumple normativa. Ve a **Conflictos**.")
    
    if not df_union.empty:
        for semestre in sorted(df_union['Semestre'].astype(str).unique()):
            st.markdown(f"#### 📅 {semestre.upper()}")
            df_sem = df_union[df_union['Semestre'] == semestre].copy()
            html_calendario = generar_html_calendario(df_sem, horas_evaluacion, df_inmutables, mapa_colores)
            st.markdown(html_calendario, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Leyenda")
        df_leyenda = df_union.drop_duplicates(subset=['Código', 'Grupo']).copy()
        for _, r in df_leyenda.iterrows():
            is_fixed = not df_inmutables.empty and ((df_inmutables['Código'] == r['Código']) & (df_inmutables['Grupo'] == r['Grupo'])).any()
            col1, col2, col3, col4 = st.columns([0.5, 3.5, 4, 1.5])
            with col1: st.markdown(f"<div style='background-color: {mapa_colores.get(r['Código'])}; width: 100%; height: 40px; border-radius: 5px; border: 1px solid #ccc;'></div>", unsafe_allow_html=True)
            with col2: st.markdown(f"**[{r['Código']}] {r['Asignatura']}**<br><span style='color: #666; font-size: 0.9em;'>Grupo: {r['Grupo']} | {r['Semestre']}</span>", unsafe_allow_html=True)
            with col3: st.markdown(f"🎓 {r['Titulación']}<br>🏫 {r['Campus']} | {r['Turno']}", unsafe_allow_html=True)
            with col4: 
                if is_fixed:
                    st.markdown("🔒 **Fija (1ª Vuelta)**") 
                else:
                    st.markdown("✨ **Nueva Elección**")
            st.markdown("---")
    else: st.info("Ve a la pestaña de Selección para añadir asignaturas.")

with tab3:
        st.subheader("📅 Calendario")
        
        if not df_union.empty:
            # --- AJUSTES DE CALENDARIO ---
            with st.expander("⚙️ Ajustes de Festivos y Fechas Compartidas", expanded=False):
                colA, colB = st.columns([1, 1])
                
                with colA:
                    st.markdown("**🏖️ Días Festivos** (Sólo los que no aparezcan en rojo en el calendario)")
                    festivos_programados = ["12/10/26", "02/11/26", "04/12/26", "07/12/26", "08/12/26", "22/03/27", "22/03/27", "23/03/27", "24/03/27", "25/03/27", "26/03/27", "29/03/27"]
                    fechas_unicas = sorted(df_union['Fecha_str'].unique(), key=lambda x: datetime.datetime.strptime(x, '%d/%m/%y'))
                    festivos_usuarios = st.multiselect("Selecciona días para eliminar del calendario:", fechas_unicas)
                    festivos = list(set(festivos_programados + festivos_usuarios))
                
                with colB:
                    st.markdown("**📅 Rango por Asignatura (Compartidas)**")
                    asignaturas_unicas = df_union[['Código', 'Asignatura', 'Grupo', 'Titulación']].drop_duplicates()
                    ajustes_asig = {}
                    
                    for _, r in asignaturas_unicas.iterrows():
                        cod_grp = f"{r['Código']}_{r['Grupo']}"
                        df_asig_fechas = df_union[(df_union['Código'] == r['Código']) & (df_union['Grupo'] == r['Grupo'])]
                        fechas_asig = sorted(df_asig_fechas['Fecha_str'].unique(), key=lambda x: datetime.datetime.strptime(x, '%d/%m/%y'))
                        
                        modo = st.radio(f"**{r['Asignatura']}** ({r['Grupo']}) {r['Titulación']}:", ["Rango", "Días sueltos"], horizontal=True, key=f"mode_{cod_grp}")
                        
                        if modo == "Rango":
                            rango = st.select_slider(f"Rango fechas:", options=fechas_asig, value=(fechas_asig[0], fechas_asig[-1]), key=f"rango_{cod_grp}")
                            ajustes_asig[cod_grp] = {"tipo": "rango", "datos": rango}
                        else:
                            seleccion = st.multiselect(f"Selecciona días exactos:", options=fechas_asig, default=fechas_asig, key=f"mult_{cod_grp}")
                            ajustes_asig[cod_grp] = {"tipo": "lista", "datos": seleccion}

            # --- APLICAR FILTROS ---
            df_cal = df_union.copy()
            if festivos: df_cal = df_cal[~df_cal['Fecha_str'].isin(festivos)]
                
            def filtrar_asig(row):
                cg = f"{row['Código']}_{row['Grupo']}"
                if cg in ajustes_asig:
                    ajuste = ajustes_asig[cg]
                    if ajuste["tipo"] == "rango":
                        f_inicio, f_fin = ajuste["datos"]
                        d_inicio = datetime.datetime.strptime(f_inicio, '%d/%m/%y')
                        d_fin = datetime.datetime.strptime(f_fin, '%d/%m/%y')
                        return d_inicio <= row['Fecha_Obj'] <= d_fin
                    else:
                        return row['Fecha_str'] in ajuste["datos"]
                return True
                
            df_cal = df_cal[df_cal.apply(filtrar_asig, axis=1)]

            # --- CÁLCULO DE HORAS REALES ---
            def calc_horas(row):
                try:
                    h1, m1 = map(int, row['Hora Inicio'].split(':'))
                    h2, m2 = map(int, row['Hora Fin'].split(':'))
                    return (h2 + m2/60.0) - (h1 + m1/60.0)
                except: return 0
                
            df_cal['Horas_Reales'] = df_cal.apply(calc_horas, axis=1)
            total_horas_reales = df_cal['Horas_Reales'].sum()
            
            

            # --- NUEVO: DESGLOSE POR GRUPO ---
            with st.expander("🔍 Desglose de horas reales impartidas", expanded=False):
                st.success(f"⏱️ **Total de Horas Reales en Calendario:** {total_horas_reales:g} h (Descontando festivos y fuera de rango)")
                if not df_cal.empty:
                    st.markdown("##### 🔍 Desglose de horas reales impartidas")
                    desglose = df_cal.groupby(['Código', 'Asignatura', 'Grupo', 'Titulación'])['Horas_Reales'].sum().reset_index()
                    
                    # Lo organizamos en 3 columnas para que quede visual y ordenado
                    cols = st.columns(3)
                    for idx, row in desglose.iterrows():
                        with cols[idx % 3]:
                            st.markdown(f"**{row['Asignatura']}**<br><span style='color:#555; '> {row['Titulación']}<br><span style='color:#555;'>Grupo {row['Grupo']}: **{row['Horas_Reales']:g} h**</span>", unsafe_allow_html=True)
                    st.markdown("<br>", unsafe_allow_html=True)

            # --- DIBUJAR CALENDARIO ACTUALIZADO ---
            if not df_cal.empty:
                df_cal['Lunes_Semana'] = df_cal['Fecha_Obj'] - pd.to_timedelta(df_cal['Fecha_Obj'].dt.weekday, unit='d')
                semanas_ordenadas = sorted(df_cal['Lunes_Semana'].dropna().unique())
                dias_activos = [d for d in ['L', 'M', 'X', 'J', 'V', 'S', 'D'] if d in df_cal['Día'].values]
                
                html_lines = []
                html_lines.append("<style>.scroll-crono { max-height: 650px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; } .ht-crono { width: 100%; border-collapse: collapse; font-family: sans-serif; table-layout: fixed; } .ht-crono th { background-color: #f0f2f6; border: 1px solid #ddd; padding: 6px; text-align: center; font-size: 0.85em; color: #31333F; position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); } .ht-crono td { border: 1px solid #ddd; padding: 4px; vertical-align: top; background-color: #ffffff; } .hc-sem { width: 90px; font-weight: bold; text-align: center; vertical-align: middle !important; background-color: #fafafa !important; font-size: 0.8em; z-index: 11; } .badge-hora { font-weight: bold; color: #111; font-size: 0.85em; margin-bottom: 3px; border-bottom: 1px dotted rgba(0,0,0,0.2); padding-bottom: 2px; }</style>")
                html_lines.append("<div class='scroll-crono'><table class='ht-crono'><tr><th class='hc-sem'>Semana</th>")
                for d in dias_activos: html_lines.append(f"<th>{d}</th>")
                html_lines.append("</tr>")
                
                for semana in semanas_ordenadas:
                    html_lines.append(f"<tr><td class='hc-sem'>Semana<br>{semana.strftime('%d/%m/%Y')}</td>")
                    for dia in dias_activos:
                        html_lines.append("<td>")
                        for _, r in df_cal[(df_cal['Lunes_Semana'] == semana) & (df_cal['Día'] == dia)].sort_values('Hora Inicio').iterrows():
                            html_lines.append(f"<div class='card-min' style='background-color: {mapa_colores.get(r['Código'], '#E3F2FD')};'><div class='badge-hora'>⏱ {r['Hora Inicio']} - {r['Hora Fin']}</div><div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div><div class='card-i'>Grupo: {r['Grupo']}</div></div>")
                        html_lines.append("</td>")
                    html_lines.append("</tr>")
                html_lines.append("</table></div>")
                st.markdown("".join(html_lines), unsafe_allow_html=True)
            else:
                st.warning("No hay clases en el calendario con los filtros de fechas actuales.")
        else:
            st.info("Ve a la pestaña de Selección para añadir asignaturas.")

with tab4:
    st.subheader("Análisis de Solapamientos, Desplazamientos y Normativa")
    if not df_union.empty:
        st.markdown("### 📜 Cumplimiento de Normativa")
        if alertas_normativa:
            st.warning("⚠️ **Avisos de Normativa:**")
            for alerta in alertas_normativa: st.write(f"- {alerta}")
        else: st.success("✅ **Normativa:** Todas las selecciones cumplen con la normativa y los límites de desdobles ocultos.")
        st.markdown("---")
        st.markdown("### 🏃‍♂️ Cruces y Desplazamientos")
        if conflictos_lista:
            st.error("⚠️ Solapamientos horarios estrictos detectados:")
            for c in conflictos_lista: st.write(f"- {c}")
        else: st.success("✅ No hay solapamientos de horario estrictos en el calendario.")
            
        if alertas_desplazamiento:
            st.warning("⚠️ Alertas de desplazamiento entre sedes (menos de 60 min de margen):")
            for a in alertas_desplazamiento: st.write(f"- {a}")
        else: st.success("✅ Los tiempos de desplazamiento entre sedes son seguros.")
    else: st.info("Sin asignaturas seleccionadas.")

with tab5:
    lista_profesores_total = sorted([p for p in df_eventos['Profesor_Original'].unique() if p != "Ninguno"])
    prof_buscado = st.selectbox("Selecciona un profesor/a para ver su carga docente:", ["-- Seleccionar --"] + lista_profesores_total)
    
    if prof_buscado != "-- Seleccionar --":
        df_prof = df_eventos[df_eventos['Profesor_Original'] == prof_buscado].copy()
        df_prof_unicos = df_prof.drop_duplicates(subset=['Código', 'Grupo'])
        horas_prof = df_prof_unicos['Horas_Profesor'].sum()
        st.markdown("---")
        info_fuerza = buscar_fuerza_profesor(prof_buscado, df_fuerza)
        fuerza_real = pd.to_numeric(info_fuerza.get('Fuerza', 240), errors='coerce') if info_fuerza is not None else 240
        fuerza_real = 240 if pd.isna(fuerza_real) or fuerza_real <= 0 else fuerza_real
        descargas = pd.to_numeric(info_fuerza.get('DescargaTotal', 0), errors='coerce') if info_fuerza is not None else 0
        descargas = 0 if pd.isna(descargas) else descargas
        porcentaje_exacto = (horas_prof / fuerza_real) * 100 if fuerza_real > 0 else 0
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1: st.metric(label="Horas asignadas", value=f"{horas_prof} h")
        with col2: st.metric(label="POD Objetivo (Fuerza)", value=f"{fuerza_real} h", delta=f"-{descargas}h reducciones" if descargas != 0 else None, delta_color="off")
        with col3:
            st.write(f"**Progreso del POD: {porcentaje_exacto:.1f}%**")
            st.progress(min(horas_prof / fuerza_real, 1.0) if fuerza_real > 0 else 0.0)
            falta = fuerza_real - horas_prof
            if falta > 9: st.warning(f"💡 **Faltan {falta}h** (Participará en siguientes vueltas).")
            elif falta > 0 and falta <= 9: st.success(f"✅ **POD completado.** (Le faltan {falta}h pero está dentro de la horquilla permitida).")
            elif horas_prof == fuerza_real: st.success("✅ **POD completado exactamente al 100%.**")
            else: st.success(f"🔥 **POD superado por {abs(falta)}h** (Por encima del 100%).")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 📅 Cuadrante Semanal del Compañero")
        for semestre in sorted(df_prof['Semestre'].astype(str).unique()):
            st.markdown(f"##### {semestre.upper()}")
            df_sem_prof = df_prof[df_prof['Semestre'] == semestre].copy()
            horas_prof_eval = {f"{r['Código']}_{r['Grupo']}": int(r['Horas_Profesor']) for _, r in df_sem_prof.drop_duplicates(subset=['Código', 'Grupo']).iterrows()}
            html_calendario_prof = generar_html_calendario(df_sem_prof, horas_prof_eval, None, mapa_colores)
            st.markdown(html_calendario_prof, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("📋 Leyenda de Asignaturas del Docente")
        
        df_leyenda_prof = df_prof.drop_duplicates(subset=['Código', 'Grupo']).copy()
        for _, r in df_leyenda_prof.iterrows():
            bg = mapa_colores.get(r['Código'], "#E3F2FD")
            col1, col2, col3 = st.columns([0.5, 4.5, 5])
            with col1: st.markdown(f"<div style='background-color: {bg}; width: 100%; height: 40px; border-radius: 5px; border: 1px solid #ccc;'></div>", unsafe_allow_html=True)
            with col2: st.markdown(f"**[{r['Código']}] {r['Asignatura']}**<br><span style='color: #666; font-size: 0.9em;'>Grupo: {r['Grupo']} | {r['Semestre']}</span>", unsafe_allow_html=True)
            with col3: st.markdown(f"🎓 {r['Titulación']}<br>🏫 {r['Campus']} | {r['Turno']}", unsafe_allow_html=True)
            st.markdown("---")

with tab6:
    st.subheader("📈 Estado Global de la Elección de POD")
    df_unicos_global = df_eventos.drop_duplicates(subset=['Código', 'Grupo'])
    total_horas_area = df_unicos_global['Horas_Totales'].sum()
    df_unicos_prof = df_eventos.drop_duplicates(subset=['Código', 'Grupo', 'Profesor_Original'])
    total_asignadas = df_unicos_prof[df_unicos_prof['Profesor_Original'] != 'Ninguno']['Horas_Profesor'].sum()
    balance = total_asignadas - total_horas_area
    signo_balance = "+" if balance > 0 else ""
    pct_global = (total_asignadas / total_horas_area) * 100 if total_horas_area > 0 else 0
    
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
                if all(p in simplificar_nombre(nom_f) for p in simplificar_nombre(nom_pod).replace(',', ' ').split()):
                    h_asig += h; profs_procesados.add(nom_pod)
            pct = min(h_asig / fuerza, 1.0) if fuerza > 0 else 0.0
            datos_profs.append({'Original_Index': row_f['Index_Orig'], 'Is_Finished': pct >= 1.0 or (fuerza - h_asig) <= 9, 'Profesor': nom_f, 'Horas Asignadas': h_asig, 'Objetivo (Fuerza)': fuerza, 'Progreso %': round((h_asig / fuerza) * 100, 1) if fuerza > 0 else 0.0, 'Ratio': pct, 'Estado': "" })
    
    for nom_pod, h in horas_por_prof.items():
        if nom_pod not in profs_procesados:
            fuerza = 240 
            pct = min(h / fuerza, 1.0)
            datos_profs.append({'Original_Index': 9999, 'Is_Finished': h >= fuerza or (fuerza - h) <= 9, 'Profesor': f"{nom_pod} (No en Excel Fuerza)", 'Horas Asignadas': h, 'Objetivo (Fuerza)': fuerza, 'Progreso %': round((h / fuerza) * 100, 1), 'Ratio': pct, 'Estado': ""})

    fuerza_activos = sum(p['Objetivo (Fuerza)'] for p in datos_profs if p['Horas Asignadas'] > 0)
    asignadas_activos = sum(p['Horas Asignadas'] for p in datos_profs if p['Horas Asignadas'] > 0)
    balance_activo = asignadas_activos - fuerza_activos

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("📚 Asig. Área", f"{total_horas_area} h")
    col2.metric("🧑‍🏫 Asignadas", f"{total_asignadas} h")
    col3.metric("⚖️ Bal. Área", f"{balance} h", delta=f"{signo_balance}{balance} h", delta_color="normal" if balance >= 0 else "inverse")
    col4.metric("⚖️ Bal. Activos", f"{balance_activo} h", delta=f"{'+' if balance_activo > 0 else ''}{balance_activo} h", delta_color="normal" if balance_activo >= 0 else "inverse")
    col5.metric("📊 Progreso", f"{pct_global:.1f} %")
    
    st.progress(min(total_asignadas / total_horas_area, 1.0) if total_horas_area > 0 else 0.0)
    st.markdown("---")
    
    if datos_profs:
        hay_profesores_sin_horas = any(p['Horas Asignadas'] == 0 and p['Original_Index'] != 9999 for p in datos_profs)
        sorted_profs = sorted(datos_profs, key=lambda x: x['Original_Index'])
        found_next = False
        
        for p in sorted_profs:
            if p['Is_Finished']: p['Estado'] = "Completado ✅"
            else:
                if hay_profesores_sin_horas:
                    if p['Horas Asignadas'] == 0:
                        if not found_next: p['Estado'] = "👉 LE TOCA ELEGIR (1ª Vuelta)"; found_next = True
                        else: p['Estado'] = "En espera ⏳ (1ª Vuelta)"
                    else: p['Estado'] = "Esperando 2ª Vuelta ⏳"
                else:
                    if not found_next: p['Estado'] = "👉 LE TOCA ELEGIR (2ª+ Vuelta)"; found_next = True
                    else: p['Estado'] = "En espera ⏳"
        
        sorted_profs_display = sorted(sorted_profs, key=lambda x: (x['Is_Finished'], x['Original_Index']))
        for p in sorted_profs_display: del p['Original_Index']; del p['Is_Finished']
        
        st.dataframe(pd.DataFrame(sorted_profs_display), column_config={"Profesor": st.column_config.TextColumn("Profesor", width="large"), "Horas Asignadas": st.column_config.NumberColumn("Asig.", format="%d h"), "Objetivo (Fuerza)": st.column_config.NumberColumn("Fuerza", format="%d h"), "Progreso %": st.column_config.NumberColumn("%", format="%.1f %%"), "Ratio": st.column_config.ProgressColumn("Progreso", format="%.2f", min_value=0, max_value=1.0), "Estado": st.column_config.TextColumn("Turno")}, use_container_width=True, hide_index=True)
