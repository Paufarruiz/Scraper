import threading
import requests
import time
import json
import os
from groq import Groq
from itertools import cycle
from dotenv import load_dotenv  # <-- Importación nueva

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN DE INFRAESTRUCTURA SEGURA ---
# Leemos las llaves desde el entorno, no desde el texto plano
LISTA_KEYS_GROQ = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4")
]
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- CARGA DINÁMICA DESDE JSON ---
CONFIG_FILE = "config_cliente.json"

def cargar_configuracion():
    if not os.path.exists(CONFIG_FILE):
        print(f"[X] ERROR: No se encuentra el archivo {CONFIG_FILE}. Crea el JSON para continuar.")
        exit()
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# Cargamos los datos del cliente al arrancar
config = cargar_configuracion()
NOMBRE_CLIENTE = config['nombre']
DOMINIOS = config['dominios']
TEMAS_VIGILANCIA = config['temas_vigilancia']

# Recursos globales
key_pool = cycle([k for k in LISTA_KEYS_GROQ if k]) # Filtra llaves vacías
file_lock = threading.Lock()
ai_semaphore = threading.Semaphore(2) 
ids_procesados = set()
INTERVALO_VIGILANCIA = 30 

def analyze_with_brain(text, fuente):
    """Nivel 2: Motor Forense"""
    with ai_semaphore:
        current_key = next(key_pool)
        client = Groq(api_key=current_key)
        
        prompt_contexto = (
            f"Eres el sistema ARGUS vigilando para '{NOMBRE_CLIENTE}'. Dominios: {DOMINIOS}. "
            "Tu objetivo es extraer datos SI Y SOLO SI aparecen en el texto. "
            "Responde en JSON: "
            '{"alerta": true/false, "tipo": "string", "claves_filtradas": ["datos_reales"]}. '
            "REGLA DE ORO: No inventes nada. Si el texto dice 'Pepe', extrae 'Pepe'. "
            "Si no hay datos claros, deja 'claves_filtradas' como lista vacía []."
        )
        
        try:
            time.sleep(0.5) 
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": prompt_contexto}, {"role": "user", "content": text}],
                model="llama-3.3-70b-versatile",
                # response_format={"type": "json_object"}, # Asegúrate que el modelo lo soporta
                temperature=0,
            )
            return json.loads(chat_completion.choices[0].message.content)
        except Exception as e:
            # print(f"Error en IA: {e}")
            return {"alerta": False, "tipo": "Error", "claves_filtradas": []}

def reddit_worker(topic):
    """Vigilancia en Reddit (Título + Cuerpo)"""
    global ids_procesados
    url = f"https://www.reddit.com/search.json?q={topic.strip()}&limit=5&sort=new"
    try:
        response = requests.get(url, headers={'User-Agent': 'Argus_V1.7'}, timeout=10)
        if response.status_code == 200:
            posts = response.json().get('data', {}).get('children', [])
            for post in posts:
                p_id = post['data']['id']
                if p_id not in ids_procesados:
                    titulo = post['data']['title']
                    cuerpo = post['data'].get('selftext', '')
                    
                    print(f"[*] [Reddit] Analizando: {titulo[:50]}...")
                    
                    texto_completo = f"TÍTULO: {titulo} | CONTENIDO: {cuerpo}"
                    res_ia = analyze_with_brain(texto_completo, "Reddit")
                    
                    if res_ia.get("alerta"):
                        print(f"\n[!!!] ALERTA EN REDDIT: {res_ia['tipo']}")
                        print(f"[DATOS] {res_ia['claves_filtradas']}\n")
                        save_alert(p_id, res_ia, f"https://reddit.com{post['data']['permalink']}", "Reddit")
                    
                    ids_procesados.add(p_id)
    except: pass

def github_worker(topic):
    """Vigilancia en GitHub"""
    global ids_procesados
    url = f"https://api.github.com/search/code?q={topic.strip()}&per_page=5"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            items = response.json().get('items', [])
            for item in items:
                f_url = item['html_url']
                if f_url not in ids_procesados:
                    print(f"[*] [GitHub] Analizando: {item['repository']['name']}")
                    contexto = f"Repo: {item['repository']['full_name']} | Path: {item['path']}"
                    res_ia = analyze_with_brain(contexto, "GitHub")
                    
                    if res_ia.get("alerta"):
                        print(f"\n[!!!] ALERTA GITHUB DETECTADA")
                        print(f"[DATOS] {res_ia['claves_filtradas']}\n")
                        save_alert(f_url, res_ia, f_url, "GitHub")
                    
                    ids_procesados.add(f_url)
    except: pass

def save_alert(id_doc, res_ia, url, fuente):
    hallazgo = {
        "cliente": NOMBRE_CLIENTE,
        "fuente": fuente,
        "amenaza": res_ia.get("tipo"),
        "datos": res_ia.get("claves_filtradas"),
        "url": url,
        "timestamp": time.ctime()
    }
    with file_lock:
        with open("log_seguridad_argus.json", "a", encoding="utf-8") as f:
            f.write(json.dumps(hallazgo) + "\n")

# --- BUCLE DE EJECUCIÓN CONTINUA ---
print(f"=== ARGUS V1.7: MODO SERVICIO ACTIVO ===")
print(f"Carga de configuración exitosa: {NOMBRE_CLIENTE}")

try:
    while True:
        print(f"\n--- Ronda de vigilancia iniciada ({time.strftime('%H:%M:%S')}) ---")
        threads = []
        for t in TEMAS_VIGILANCIA:
            threads.append(threading.Thread(target=reddit_worker, args=(t,)))
            threads.append(threading.Thread(target=github_worker, args=(t,)))
        
        for t in threads: t.start()
        for t in threads: t.join()
        
        print(f"[*] Ronda finalizada. Esperando {INTERVALO_VIGILANCIA}s...")
        time.sleep(INTERVALO_VIGILANCIA)
except KeyboardInterrupt:
    print("\n[!] Servicio detenido.")