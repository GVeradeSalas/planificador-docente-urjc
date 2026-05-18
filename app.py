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
                    'Asignatura': row.get('Nombre Asignatura', 'Desconocido'),
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
                    'Asignatura': row.get('Nombre Asignatura', 'Desconocido'),
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
        
        # --- NUEVO: DESLIZADORES DINÁMICOS DE HORAS ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("Ajuste de Horas a Impartir")
        
        horas_asumidas_dict = {}
        for _, r in df_unicos.iterrows():
            max_h = int(r['Horas_Disponibles'])
            titulo_slider = f"{r['Asignatura']} ({r['Grupo']})"
            
            # El deslizador permite elegir desde 0 hasta el máximo de horas disponibles
            horas_elegidas = st.sidebar.slider(
                titulo_slider, 
                min_value=0, 
                max_value=max_h, 
                value=max_h, 
                step=1
            )
            horas_asumidas_dict[r['Asig_Grupo']] = horas_elegidas
            
        horas_totales_asumidas = sum(horas_asumidas_dict.values())
        horas_nominales = df_unicos['Horas_Totales'].sum()
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Resumen de Carga Docente")
        st.sidebar.metric(label="⏱️ Horas Docentes Asumidas", value=f"{horas_totales_asumidas} h")
        st.sidebar.caption(f"Horas totales del conjunto de grupos: {horas_nominales} h")
        
        tab1, tab2, tab3 = st.tabs([
            "⏰ Cuadrante Horario Semanal", 
            "📅 Calendario Semana a Semana", 
            "📊 Análisis de Conflictos"
        ])
        
        with tab1:
            st.subheader("Distribución de Horas por Tramo Semanal")
            st.write("Consolidación horaria de los grupos seleccionados.")
            
            df_seleccion['Franja Horaria'] = df_seleccion['Hora Inicio'] + " - " + df_seleccion['Hora Fin']
            
            def consolidar_bloques_semanales(sub_df):
                lineas = []
                for _, r in sub_df.drop_duplicates(subset=['Código', 'Grupo']).iterrows():
                    h_asumidas = horas_asumidas_dict.get(r['Asig_Grupo'], r['Horas_Disponibles'])
                    lineas.append(f"[{r['Código']}] {r['Asignatura']} ({r['Grupo']})\nAsumes: {h_asumidas}h (de {r['Horas_Disponibles']} disp.)")
                return "\n\n".join(lineas)
            
            df_pivot_semanal = df_seleccion.groupby(['Franja Horaria', 'Día']).apply(consolidar_bloques_semanales).reset_index(name='Contenido')
            df_cuadrante_fijo = df_pivot_semanal.pivot(index='Franja Horaria', columns='Día', values='Contenido').fillna("-")
            
            dias_semana = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
            columnas_ordenadas = [d for d in dias_semana if d in df_cuadrante_fijo.columns]
            df_cuadrante_fijo = df_cuadrante_fijo[columnas_ordenadas]
            df_cuadrante_fijo = df_cuadrante_fijo.sort_index()
            
            st.dataframe(df_cuadrante_fijo, use_container_width=True, height=450)

        with tab2:
            st.subheader("Seguimiento por Fechas Exactas")
            st.write("Estructura por semanas naturales para vigilar alternancias en el calendario.")
            
            df_seleccion['Lunes_Semana'] = df_seleccion['Fecha_Obj'] - pd.to_timedelta(df_seleccion['Fecha_Obj'].dt.weekday, unit='d')
            
            def agrupar_fechas_cronologicas(sub_df):
                clases = sub_df.sort_values('Hora Inicio')
                lineas = []
                for _, r in clases.iterrows():
                    lineas.append(f"[{r['Código']}] {r['Asignatura']} ({r['Grupo']}) [{r['Hora Inicio']} - {r['Hora Fin']}]")
                return "\n\n".join(lineas)
                
            df_pivot_cronologico = df_seleccion.groupby(['Lunes_Semana', 'Día']).apply(agrupar_fechas_cronologicas).reset_index(name='Clases')
            df_cuadrante_crono = df_pivot_cronologico.pivot(index='Lunes_Semana', columns='Día', values='Clases').fillna("-")
            columnas_crono = [d for d in dias_semana if d in df_cuadrante_crono.columns]
            df_cuadrante_crono = df_cuadrante_crono[columnas_crono]
            
            df_cuadrante_crono.index = "Semana " + df_cuadrante_crono.index.strftime('%d/%m/%Y')
            df_cuadrante_crono.index.name = "Semana"
            
            st.dataframe(df_cuadrante_crono, use_container_width=True, height=500)

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