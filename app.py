import streamlit as st
import pandas as pd
import re

st.set_page_config(layout="wide", page_title="Planificador POD")
st.title("Planificador Docente - Análisis de Compatibilidad y Ocupación")

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
                titulo_slider, 
                min_value=0, 
                max_value=max_h, 
                value=max_h, 
                step=1,
                key=clave_unica
            )
            horas_asumidas_dict[r['Asig_Grupo']] = horas_elegidas
            
        horas_totales_asumidas = sum(horas_asumidas_dict.values())
        horas_nominales = df_unicos['Horas_Totales'].sum()
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Resumen de Carga Docente")
        st.sidebar.metric(label="⏱️ Horas Docentes Asumidas", value=f"{horas_totales_asumidas} h")
        st.sidebar.caption(f"Horas totales del conjunto de grupos: {horas_nominales} h")
        
        # --- DEFINICIÓN DE COLORES COMPARTIDA ENTRE PESTAÑAS ---
        paleta = ["#E3F2FD", "#E8F5E9", "#FFF3E0", "#FCE4EC", "#F3E5F5", "#E0F2F1", "#FFF8E1", "#FBE9E7", "#ECEFF1"]
        codigos_unicos = df_seleccion['Código'].unique()
        mapa_colores = {codigo: paleta[i % len(paleta)] for i, codigo in enumerate(codigos_unicos)}

        tab1, tab2, tab3 = st.tabs([
            "⏰ Cuadrante Horario Semanal", 
            "📅 Calendario Semana a Semana", 
            "📊 Análisis de Conflictos"
        ])
        
        with tab1:
            st.subheader("Distribución de Horas por Tramo Semanal")
            st.write("Si hay varias opciones en la misma hora, aparecerán apiladas de forma compacta.")
            
            df_seleccion['Franja Horaria'] = df_seleccion['Hora Inicio'] + " - " + df_seleccion['Hora Fin']
            franjas_ordenadas = sorted(df_seleccion['Franja Horaria'].unique())
            dias_semana = ['L', 'M', 'X', 'J', 'V']
            
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

        with tab2:
            st.subheader("Seguimiento por Fechas Exactas")
            st.write("Visualización cronológica semana a semana con tarjetas adaptables.")
            
            # 1. Calculamos el lunes de la semana para cada clase
            df_seleccion['Lunes_Semana'] = df_seleccion['Fecha_Obj'] - pd.to_timedelta(df_seleccion['Fecha_Obj'].dt.weekday, unit='d')
            semanas_ordenadas = sorted(df_seleccion['Lunes_Semana'].dropna().unique())
            
            # 2. Mostramos SOLO los días que tienen clases para no estirar la tabla a lo tonto
            dias_semana_full = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
            dias_activos = [d for d in dias_semana_full if d in df_seleccion['Día'].values]
            
            # 3. Construimos el HTML. (Ojo a position: sticky; en th para fijar la cabecera)
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
                        bg_color = mapa_colores.get(r['Código'], "#E3F2FD") # Mismo color que en la pestaña 1
                        
                        html_crono += f"<div class='card-min' style='background-color: {bg_color};'>"
                        html_crono += f"<div class='badge-hora'>⏱ {r['Hora Inicio']} - {r['Hora Fin']}</div>"
                        html_crono += f"<div class='card-t' title='[{r['Código']}] {r['Asignatura']}'>[{r['Código']}] {r['Asignatura']}</div>"
                        html_crono += f"<div class='card-i'>Grupo: {r['Grupo']}</div>"
                        html_crono += "</div>"
                        
                    html_crono += "</td>"
                html_crono += "</tr>"
                
            html_crono += "</table></div>"
            st.markdown(html_crono, unsafe_allow_html=True)

        with tab3:
            st.subheader("Análisis de Solapamientos")
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
                                un_id1 = f"[{clases[i]['Código']}] {clases[i]['Asignatura']} ({clases[i]['Grupo']})"
                                un_id2 = f"[{clases[j]['Código']}] {clases[j]['Asignatura']} ({clases[j]['Grupo']})"
                                conflictos.append({
                                    'Fecha': fecha,
                                    'Conflicto': f"{un_id1} ({inicio1}-{fin1}) se cruza con {un_id2} ({inicio2}-{fin2})"
                                })

            if conflictos:
                st.error("⚠️ ¡Atención! Se han detectado solapamientos en las fechas seleccionadas.")
                for c in conflictos:
                    st.write(f"**{c['Fecha']}:** {c['Conflicto']}")
            else:
                st.success("✅ Todas las asignaturas seleccionadas son perfectamente compatibles en las fechas del calendario.")

            st.dataframe(
                df_seleccion_ordenada[['Fecha_str', 'Hora Inicio', 'Hora Fin', 'Código', 'Asignatura', 'Grupo', 'Profesor_Original', 'Horas_Disponibles', 'Campus']], 
                use_container_width=True
            )

    else:
        st.info("👈 Utiliza el menú lateral para configurar los filtros y seleccionar los grupos con sus respectivos estados de vacantes.")
