import os, threading, csv, datetime, re, uuid, json, unicodedata, psycopg2
from collections import Counter, defaultdict
from flask import Flask, send_from_directory, request, send_file, redirect
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA","telemont2026")
DATABASE_URL = os.environ.get("DATABASE_URL")
ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros.csv"
ARQ_INS = "inspecoes.csv"
ARQ_PEDIDOS = "pedidos_mascaras.csv"
ARQ_JUST = "justificativas.csv"
PASTA_MASC = "mascaras"
BANNER = "banner.jpg"
ARQ_SUP_EMAIL = "supervisores.csv"
os.makedirs(PASTA_MASC, exist_ok=True)

# --- SUPABASE ---
def get_conn():
    if not DATABASE_URL: return None
    try: return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Erro DB: {e}")
        return None

def criar_tabelas():
    conn = get_conn()
    if not conn:
        print("SEM DATABASE_URL - modo CSV")
        return
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS inspecoes (
        id SERIAL PRIMARY KEY, data TIMESTAMP DEFAULT NOW(),
        chapa TEXT, nome TEXT, cargo TEXT, supervisor TEXT, coordenador TEXT,
        telefone TEXT, eh_motorista TEXT, item TEXT, tamanho TEXT, data_fab TEXT, validade TEXT, status TEXT
    );
    CREATE TABLE IF NOT EXISTS cadastros (
        chapa TEXT PRIMARY KEY, nome TEXT, cargo TEXT, data_admissao TEXT,
        supervisor TEXT, coordenador TEXT, telefone TEXT, id_telegram TEXT, eh_motorista TEXT
    );
    CREATE TABLE IF NOT EXISTS pedidos_mascaras (
        id SERIAL PRIMARY KEY, data TIMESTAMP DEFAULT NOW(),
        chapa TEXT, nome TEXT, telefone TEXT, supervisor TEXT, mascara_txt TEXT
    );
    CREATE TABLE IF NOT EXISTS justificativas (
        id SERIAL PRIMARY KEY, data TIMESTAMP DEFAULT NOW(),
        chapa TEXT, nome TEXT, supervisor TEXT, coordenador TEXT, motivo TEXT
    );
    """)
    conn.commit(); cur.close(); conn.close()
    print("Supabase OK!")

try: criar_tabelas()
except Exception as e: print(e)

FUNCIONARIOS = {}
SUPERVISORES_LISTA = set()
COORDENADORES_LISTA = set()

def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
def gerar_email_telemont(nome_completo):
    nome = remover_acentos(nome_completo.upper())
    partes = [p for p in nome.split() if p not in ["DE","DA","DO","DOS","DAS","E"]]
    if len(partes) == 1:
        return f"{partes[0].lower()}@telemont.com.br"
    return f"{partes[0].lower()}.{partes[-1].lower()}@telemont.com.br"

def carregar_funcionarios():
    global FUNCIONARIOS, SUPERVISORES_LISTA, COORDENADORES_LISTA
    FUNCIONARIOS.clear(); SUPERVISORES_LISTA.clear(); COORDENADORES_LISTA.clear()
    try:
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline()
            delim = ";" if ";" in primeira else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            reader.fieldnames = [c.strip().lower().replace("\ufeff","").replace(" ","_") for c in reader.fieldnames]
            ch_col = reader.fieldnames[0]
            nome_col = next((c for c in reader.fieldnames if "nome" in c), None)
            sup_col = next((c for c in reader.fieldnames if "superv" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c or "gerent" in c), None)
            cargo_col = next((c for c in reader.fieldnames if "cargo" in c), None)
            adm_col = next((c for c in reader.fieldnames if "admiss" in c), None)
            for r in reader:
                try:
                    chapa_raw = str(r.get(ch_col,"")).strip()
                    if not chapa_raw: continue
                    chapa_6 = chapa_raw.zfill(6)
                    nome_sup = str(r.get(sup_col,"")).strip().upper()
                    nome_coord = str(r.get(coord_col,"")).strip().upper()
                    if nome_sup: SUPERVISORES_LISTA.add(nome_sup)
                    if nome_coord: COORDENADORES_LISTA.add(nome_coord)
                    FUNCIONARIOS[chapa_6] = {"nome": str(r.get(nome_col,"")).strip().upper(),"cargo": str(r.get(cargo_col,"")).strip().upper(),"admissao": str(r.get(adm_col,"")).strip(),"supervisor": nome_sup,"coordenador": nome_coord}
                    FUNCIONARIOS[chapa_raw] = FUNCIONARIOS[chapa_6]
                except: continue
    except: pass
carregar_funcionarios()

EMAILS_SUP = {}
def carregar_emails_sup():
    global EMAILS_SUP
    EMAILS_SUP={}
    for sup in SUPERVISORES_LISTA:
        if sup: EMAILS_SUP[sup] = gerar_email_telemont(sup)
    for coord in COORDENADORES_LISTA:
        if coord: EMAILS_SUP[coord] = gerar_email_telemont(coord)
    try:
        with open(ARQ_SUP_EMAIL, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sup = str(r.get('supervisor','')).strip().upper()
                email = str(r.get('email','')).strip()
                if sup and email: EMAILS_SUP[sup] = email
    except: pass
carregar_emails_sup()

for arq, head in [(ARQ_CAD, ["chapa","nome","cargo","data_admissao","supervisor","coordenador","telefone","id_telegram","eh_motorista"]), (ARQ_INS, ["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"]), (ARQ_PEDIDOS, ["data","chapa","nome","telefone","supervisor","mascara_txt"]), (ARQ_JUST, ["data","chapa","nome","supervisor","coordenador","motivo"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(head)

# SEU CODIGO ORIGINAL CONTINUA IGUAL...
ITENS = [
    {"nome":"CALÇADO DE SEGURANÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False},
    {"nome":"CAPACETE DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5},
    {"nome":"CARNEIRA/JUGULAR", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"ÓCULOS DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"COLETE REFLETIVO", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"LUVA DE RASPA", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"CINTO DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5},
    {"nome":"TALABARTE DE POSICIONAMENTO", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5},
    {"nome":"CAPA DE CHUVA", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"BOTA DE PVC", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False},
    {"nome":"PERNEIRA", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"ESCADA DUPLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"BANDEIROLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"CONES DE SINALIZAÇÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "auto_cone":True},
    {"nome":"TRAVA QUEDAS", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5},
    {"nome":"PROTETOR SOLAR", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"GARRA MEIO DE VÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"DETECTOR DE TENSÃO", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"VARA DE MANOBRA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"CHAVE J", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"CHAVE T", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"CORDA 20M", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"FITA AMARRAÇÃO ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"FITA DE ANCORAGEM EUREKA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"FREIO ABS", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"MOSQUETÃO", "regra":"APENAS MOTORISTA", "tamanho":True, "tamanho_tipo":"QTD", "label_tamanho":"QUANTIDADE (1, 2 ou 3)", "data_fab":False, "auto_mosquetao":True},
    {"nome":"CORREIA PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"CORDIM PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"FITA DE ANCORAGEM 1,5M", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"SACOLA NYLON", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False},
    {"nome":"BOLSA TIRACOLO", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"CAMISA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"LETRAS3", "data_fab":False},
    {"nome":"CALÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False},
    {"nome":"CRACHÁ PADRÃO TELEMONT", "regra":"TODOS", "tamanho":False, "data_fab":False},
    {"nome":"BOLSA DE EPI", "regra":"TODOS", "tamanho":False, "data_fab":False},
]

CHAPA, TELEFONE, EH_MOTORISTA, TAMANHO, DATA_FAB, STATUS, CONE_TIPO, CONE_QTD = range(8)

def buscar_func(chapa):
    c = str(chapa).strip().zfill(6)
    return FUNCIONARIOS.get(c) or FUNCIONARIOS.get(str(chapa).strip())

def ja_inspecionou(chapa):
    ch6 = str(chapa).zfill(6)
    conn = get_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM inspecoes WHERE chapa=%s LIMIT 1", (ch6,))
            r = cur.fetchone()
            cur.close(); conn.close()
            if r: return True
        except: pass
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("chapa","")).zfill(6) == ch6: return True
    except: pass
    return False

def buscar_cadastro(chapa):
    ch6 = str(chapa).zfill(6)
    conn = get_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM cadastros WHERE chapa=%s", (ch6,))
            row = cur.fetchone()
            if row:
                cur.close(); conn.close()
                return {"chapa":row[0],"nome":row[1],"telefone":row[6]}
        except: pass
    try:
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["chapa"].zfill(6)==ch6: return r
    except: pass
    return None

def salvar_cadastro(d):
    conn = get_conn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cadastros (chapa,nome,cargo,data_admissao,supervisor,coordenador,telefone,id_telegram,eh_motorista)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (chapa) DO UPDATE SET nome=EXCLUDED.nome, telefone=EXCLUDED.telefone, eh_motorista=EXCLUDED.eh_motorista
            """, (d["chapa"],d["nome"],d["cargo"],d["data_admissao"],d["supervisor"],d["coordenador"],d["telefone"],d["id_telegram"],d["eh_motorista"]))
            conn.commit(); cur.close(); conn.close()
        except Exception as e: print(f"Erro salvar cadastro: {e}")
    rows=[]
    try:
        with open(ARQ_CAD, encoding="utf-8") as f: rows=list(csv.DictReader(f))
    except: pass
    rows=[r for r in rows if r["chapa"].zfill(6)!=d["chapa"].zfill(6)]
    rows.append(d)
    with open(ARQ_CAD, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=["chapa","nome","cargo","data_admissao","supervisor","coordenador","telefone","id_telegram","eh_motorista"])
        w.writeheader(); w.writerows(rows)

def validar_tamanho(valor, tipo):
    valor=valor.strip().upper()
    if tipo=="NUM2" or tipo=="QTD":
        if not valor.isdigit(): return False, "Só números!"
        return True, valor
    if tipo=="LETRAS3":
        if not valor.isalpha(): return False, "Só letras!"
        return True, valor
    return True, valor

def calcular_validade(data_str, anos=5):
    try:
        dt = datetime.datetime.strptime(data_str, "%d/%m/%Y")
        venc = dt + datetime.timedelta(days=anos*365)
        return venc.strftime("%d/%m/%Y"), venc < datetime.datetime.now()
    except: return "", False

def get_justificados():
    just={}
    conn = get_conn()
    if conn:
        try:
            cur=conn.cursor(); cur.execute("SELECT chapa, motivo FROM justificativas")
            for ch, mot in cur.fetchall(): just[str(ch).zfill(6)]={"chapa":ch,"motivo":mot}
            cur.close(); conn.close()
            if just: return just
        except: pass
    try:
        with open(ARQ_JUST, encoding="utf-8") as f:
            for r in csv.DictReader(f): just[str(r.get('chapa','')).zfill(6)] = r
    except: pass
    return just

def gerar_mascara_txt(dados_colab, lista_nao_conforme):
    txt = f"""========================================
    PEDIDO DE EPI - NÃO CONFORME - SESMT
DATA/HORA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
CHAPA: {dados_colab['chapa']}
NOME: {dados_colab['nome']}
SUPERVISOR: {dados_colab['supervisor']}
COORDENADOR: {dados_colab.get('coordenador','')}
TOTAL NÃO CONFORME: {len(lista_nao_conforme)}
"""
    if not lista_nao_conforme: txt += "NENHUM - TODOS CONFORME\n"
    else:
        for i, r in enumerate(lista_nao_conforme, 1): txt += f"{i}. {r['item']} - {r.get('status')}\n"
    nome_arq = f"MASCARA_{dados_colab['chapa']}_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}_{uuid.uuid4().hex[:4]}.txt"
    caminho = os.path.join(PASTA_MASC, nome_arq)
    with open(caminho, "w", encoding="utf-8") as f: f.write(txt)
    return caminho, txt

def enviar_email_nao_conforme(supervisor_nome, coordenador_nome, chapa, nome_colab, lista_nao_conforme, caminho_txt, dados_colab):
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        email_sup = EMAILS_SUP.get(supervisor_nome.upper()) if supervisor_nome else None
        EMAIL_CC = os.environ.get("EMAIL_CC","").strip()
        emails_destino = []
        if email_sup: emails_destino.append(email_sup)
        if EMAIL_CC: emails_destino.append(EMAIL_CC)
        if not emails_destino: return False, []
        EMAIL_USER = os.environ.get("EMAIL_USER", "").strip() or "botsesmt@gmail.com"
        EMAIL_PASS = os.environ.get("EMAIL_PASS", "").strip().replace(" ","") or "tcepcskwinxlfnsk"
        SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
        SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        assunto = f"{'NÃO CONFORME' if lista_nao_conforme else 'CONFORME'} - CHAPA {chapa} - {nome_colab}"
        corpo = f"CHAPA: {chapa}\nNOME: {nome_colab}\nSUPERVISOR: {supervisor_nome}\nCOORD: {coordenador_nome}\nTOTAL NC: {len(lista_nao_conforme)}\n"
        for r in lista_nao_conforme: corpo += f"- {r['item']}\n"
        msg = MIMEMultipart(); msg['From'] = EMAIL_USER; msg['To'] = ", ".join(emails_destino); msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
        if caminho_txt and os.path.exists(caminho_txt):
            with open(caminho_txt, "rb") as f:
                part = MIMEBase('application', 'octet-stream'); part.set_payload(f.read())
            encoders.encode_base64(part); part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(caminho_txt)}"); msg.attach(part)
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20); server.starttls(); server.login(EMAIL_USER, EMAIL_PASS); server.sendmail(EMAIL_USER, emails_destino, msg.as_string()); server.quit()
        return True, emails_destino
    except Exception as e:
        print(f"Erro email: {e}"); return False, []

# [COPIE O RESTO DO SEU CODIGO FLASK + TELEGRAM IGUAL - SÓ TROQUE O finalizar ABAIXO]

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return f"BOT SESMT ON - <a href='/base'>BASE ESTATISTICA</a> | <a href='/graficos'>GRAFICOS</a> | <a href='/admin?senha={ADMIN_SENHA}'>ADMIN</a>"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)

def carregar_inspecoes_lista(filtro_sup="", filtro_coord=""):
    lista=[]
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor()
            sql="SELECT data,chapa,nome,cargo,supervisor,coordenador,telefone,eh_motorista,item,tamanho,data_fab,validade,status FROM inspecoes"
            where=[]
            if filtro_sup: where.append(f"supervisor ILIKE '%{filtro_sup}%'")
            if filtro_coord: where.append(f"coordenador ILIKE '%{filtro_coord}%'")
            if where: sql+=" WHERE "+" AND ".join(where)
            cur.execute(sql)
            cols=["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"]
            for row in cur.fetchall(): lista.append(dict(zip(cols,row)))
            cur.close(); conn.close()
            if lista: return lista
        except Exception as e: print(e)
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sup=str(r.get('supervisor','')).upper(); coord=str(r.get('coordenador','')).upper()
                if filtro_sup and filtro_sup not in sup: continue
                if filtro_coord and filtro_coord not in coord: continue
                lista.append(r)
    except: pass
    return lista

# [MANTENHA SUAS ROTAS /base /graficos /admin iguais mas use carregar_inspecoes_lista()]
# Para não ficar gigante, use o resto do seu arquivo original aqui. O mais importante já está convertido: ja_inspecionou, salvar_cadastro, get_justificados, carregar_inspecoes_lista

# ... COLE AQUI O RESTO DAS SUAS ROTAS /base /graficos /admin /excel que você já tem, mas troque onde lê ARQ_INS por carregar_inspecoes_lista()

# FINALIZAR ATUALIZADO COM SUPABASE
async def finalizar(update, context):
    await update.message.reply_text("⏳ Salvando no Supabase...")
    chapa=context.user_data['chapa']; func=context.user_data['func']; tel=context.user_data['telefone']; eh_mot=context.user_data['eh_motorista']
    resultados=context.user_data['resultados']; nao_conf=context.user_data['nao_conforme_lista']
    data_hora=datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor()
            for r in resultados:
                cur.execute("INSERT INTO inspecoes (data,chapa,nome,cargo,supervisor,coordenador,telefone,eh_motorista,item,tamanho,data_fab,validade,status) VALUES (NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, eh_mot, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status']))
            conn.commit(); cur.close(); conn.close()
        except Exception as e: print(f"Erro salvar Supabase: {e}")
    with open(ARQ_INS, "a", newline="", encoding="utf-8") as f:
        w=csv.writer(f)
        for r in resultados: w.writerow([data_hora, chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, eh_mot, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status']])
    dados_colab={"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"eh_motorista":eh_mot}
    caminho_txt, txt_conteudo = gerar_mascara_txt(dados_colab, nao_conf)
    with open(ARQ_PEDIDOS, "a", newline="", encoding="utf-8") as f: csv.writer(f).writerow([data_hora, chapa, func['nome'], tel, func['supervisor'], txt_conteudo.replace("\n"," | ")])
    enviado=False; dest=[]
    if nao_conf:
        await update.message.reply_text(f"📧 Enviando e-mail para {func['supervisor']}...")
        enviado, dest = enviar_email_nao_conforme(func['supervisor'], func['coordenador'], chapa, func['nome'], nao_conf, caminho_txt, dados_colab)
    msg=f"✅ FINALIZADA E SALVA NO SUPABASE!\nCHAPA: {chapa}\nNÃO CONFORME: {len(nao_conf)}\n\n{txt_conteudo}"
    if enviado: msg+=f"\n\n📧 E-mail: {', '.join(dest)}"
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt))
    kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
    await update.message.reply_text("👇 Para nova inspeção:", reply_markup=kb)
    return ConversationHandler.END

# [RESTO DO SEU CODIGO TELEGRAM - start, chapa_step, telefone_step etc COLE IGUAL]
