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

def get_conn():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Erro DB: {e}")
        return None

def criar_tabelas():
    conn = get_conn()
    if not conn:
        print("SEM DATABASE_URL - modo CSV")
        return
    cur = conn.cursor()
    cur.execute('''
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
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("Supabase OK!")

try:
    criar_tabelas()
except Exception as e:
    print(e)

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
    ch6=str(chapa).zfill(6)
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor()
            cur.execute("SELECT 1 FROM inspecoes WHERE chapa=%s LIMIT 1",(ch6,))
            r=cur.fetchone()
            cur.close(); conn.close()
            if r: return True
        except: pass
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("chapa","")).zfill(6)==ch6: return True
    except: pass
    return False

def buscar_cadastro(chapa):
    try:
        with open(ARQ_CAD, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["chapa"].zfill(6)==str(chapa).zfill(6): return r
    except: pass
    return None

def salvar_cadastro(d):
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor()
            cur.execute("INSERT INTO cadastros (chapa,nome,cargo,data_admissao,supervisor,coordenador,telefone,id_telegram,eh_motorista) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (chapa) DO UPDATE SET telefone=EXCLUDED.telefone, eh_motorista=EXCLUDED.eh_motorista", (d["chapa"],d["nome"],d["cargo"],d["data_admissao"],d["supervisor"],d["coordenador"],d["telefone"],d["id_telegram"],d["eh_motorista"]))
            conn.commit(); cur.close(); conn.close()
        except: pass
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
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor(); cur.execute("SELECT chapa, motivo FROM justificativas")
            for ch,mot in cur.fetchall(): just[str(ch).zfill(6)]={"chapa":ch,"motivo":mot}
            cur.close(); conn.close()
            if just: return just
        except: pass
    try:
        with open(ARQ_JUST, encoding="utf-8") as f:
            for r in csv.DictReader(f): just[str(r.get('chapa','')).zfill(6)]=r
    except: pass
    return just

def gerar_mascara_txt(dados_colab, lista_nao_conforme):
    txt = f"PEDIDO DE EPI - NAO CONFORME - SESMT\nDATA/HORA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\nCHAPA: {dados_colab['chapa']}\nNOME: {dados_colab['nome']}\nSUPERVISOR: {dados_colab['supervisor']}\nCOORDENADOR: {dados_colab.get('coordenador','')}\nTOTAL NAO CONFORME: {len(lista_nao_conforme)}\n"
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
        assunto = f"{'NAO CONFORME' if lista_nao_conforme else 'CONFORME'} - CHAPA {chapa} - {nome_colab}"
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

def carregar_inspecoes_lista(filtro_sup="", filtro_coord=""):
    lista=[]; conn=get_conn()
    if conn:
        try:
            cur=conn.cursor(); sql="SELECT data,chapa,nome,cargo,supervisor,coordenador,telefone,eh_motorista,item,tamanho,data_fab,validade,status FROM inspecoes"; where=[]
            if filtro_sup: where.append(f"supervisor ILIKE '%{filtro_sup}%'")
            if filtro_coord: where.append(f"coordenador ILIKE '%{filtro_coord}%'")
            if where: sql+=" WHERE "+" AND ".join(where)
            cur.execute(sql); cols=["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"]
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

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return f"BOT SESMT ON - <a href='/base'>BASE ESTATISTICA</a> | <a href='/graficos'>GRAFICOS</a> | <a href='/admin?senha={ADMIN_SENHA}'>ADMIN</a>"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)

def gerar_excel_completo(caminho="/tmp/sesmt_completo.xlsx", filtro_supervisor="", filtro_coordenador=""):
    try: import pandas as pd
    except: return None
    linhas=carregar_inspecoes_lista(filtro_supervisor, filtro_coordenador)
    if not linhas: return None
    df = pd.DataFrame(linhas)
    df_nc = df[df['status']=='Não Conforme']
    resumo = df_nc.groupby('item').size().reset_index(name='QTD_NAO_CONFORME').sort_values('QTD_NAO_CONFORME', ascending=False)
    with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
        resumo.to_excel(writer, sheet_name='RESUMO_NAO_CONFORME', index=False)
        df.to_excel(writer, sheet_name='DETALHADO_FILTRADO', index=False)
        df_nc.to_excel(writer, sheet_name='SO_NAO_CONFORME', index=False)
    return caminho

@app_flask.route('/excel')
def excel_route():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper() or request.args.get('gerente','').strip().upper()
    caminho = gerar_excel_completo(filtro_supervisor=filtro_sup, filtro_coordenador=filtro_coord)
    if not caminho or not os.path.exists(caminho): return "Sem dados"
    nome = f"SESMT_{filtro_sup or 'TODOS'}_{filtro_coord or 'TODOS'}_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}.xlsx"
    return send_file(caminho, as_attachment=True, download_name=nome)

@app_flask.route('/base')
def base():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper()
    inspecoes = carregar_inspecoes_lista(filtro_sup, filtro_coord)
    feitos = set([str(r.get('chapa','')).zfill(6) for r in inspecoes])
    por_supervisor = defaultdict(list)
    chapas_unicas = {}
    for chapa_key, dados in FUNCIONARIOS.items():
        ch6 = chapa_key.zfill(6)
        if len(ch6)!=6: continue
        if ch6 in chapas_unicas: continue
        chapas_unicas[ch6] = dados
        sup = dados.get('supervisor','SEM SUPERVISOR')
        coord = dados.get('coordenador','SEM COORDENADOR')
        if filtro_sup and filtro_sup not in sup: continue
        if filtro_coord and filtro_coord not in coord: continue
        por_supervisor[sup].append({'chapa':ch6})
    justificados = get_justificados()
    todos_sup = sorted(SUPERVISORES_LISTA)
    todos_coord = sorted(COORDENADORES_LISTA)
    opt_sup = "".join([f"<option value='{s}' {'selected' if s==filtro_sup else ''}>{s}</option>" for s in todos_sup])
    opt_coord = "".join([f"<option value='{c}' {'selected' if c==filtro_coord else ''}>{c}</option>" for c in todos_coord])
    html = f"<html><head><meta charset='utf-8'><title>BASE</title><style>body{{font-family:Arial;padding:15px;background:#f0f2f5}} .card{{background:white;padding:15px;border-radius:10px;margin-bottom:20px}} table{{width:100%;border-collapse:collapse;background:white;font-size:12px}} th,td{{border:1px solid #ddd;padding:7px}} th{{background:#0F4C8F;color:white}} .btn{{padding:8px 14px;border-radius:5px;color:white;text-decoration:none;display:inline-block;font-size:12px;margin:2px}} .badge{{padding:3px 8px;border-radius:10px;color:white;font-weight:bold}}</style></head><body><h2>BASE ESTATISTICA - SUPABASE</h2><div class='card'><form method='get'>SUP: <select name='supervisor'><option value=''>TODOS</option>{opt_sup}</select> COORD: <select name='coordenador'><option value=''>TODOS</option>{opt_coord}</select><button class='btn' style='background:#0F4C8F'>FILTRAR</button><a class='btn' style='background:#6c757d' href='/base'>Limpar</a></form></div>"
    html += "<div class='card'><table><tr><th>SUPERVISOR</th><th>TOTAL</th><th>FEITOS</th><th>JUST</th><th>PEND</th><th>%</th></tr>"
    for sup, lista in sorted(por_supervisor.items()):
        total=len(lista); feitos_sup=sum(1 for c in lista if c['chapa'] in feitos); just_sup=sum(1 for c in lista if c['chapa'] in justificados); pend=total-feitos_sup-just_sup; perc=int((feitos_sup+just_sup)/total*100) if total else 0
        html+=f"<tr><td>{sup}</td><td>{total}</td><td>{feitos_sup}</td><td>{just_sup}</td><td>{pend}</td><td>{perc}%</td></tr>"
    html+="</table></div></body></html>"
    return html

@app_flask.route('/admin')
def admin_panel():
    senha = request.args.get('senha','')
    if senha != ADMIN_SENHA: return "<form><input type='password' name='senha'><button>Entrar</button></form>"
    inspecoes=carregar_inspecoes_lista()
    return f"<h2>ADMIN SUPABASE</h2><p>Total registros: {len(inspecoes)}</p><a href='/base'>BASE</a> | <a href='/graficos'>GRAFICOS</a><br><br><form action='/admin/liberar'><input type='hidden' name='senha' value='{ADMIN_SENHA}'><input name='chapa' placeholder='CHAPA'><button>LIBERAR</button></form><form action='/admin/zerar'><input type='hidden' name='senha' value='{ADMIN_SENHA}'><input name='confirmar' placeholder='ZERAR'><button>ZERAR</button></form>"

@app_flask.route('/admin/liberar')
def admin_liberar():
    senha=request.args.get('senha','')
    if senha!=ADMIN_SENHA: return "Senha invalida"
    chapa=str(request.args.get('chapa','')).zfill(6)
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor(); cur.execute("DELETE FROM inspecoes WHERE chapa=%s",(chapa,)); cur.execute("DELETE FROM justificativas WHERE chapa=%s",(chapa,)); cur.execute("DELETE FROM cadastros WHERE chapa=%s",(chapa,)); conn.commit(); cur.close(); conn.close()
        except: pass
    return f"<script>alert('Liberada {chapa}');window.location='/admin?senha={ADMIN_SENHA}';</script>"

@app_flask.route('/admin/zerar')
def admin_zerar():
    senha=request.args.get('senha',''); confirmar=request.args.get('confirmar','')
    if senha!=ADMIN_SENHA or confirmar.upper()!="ZERAR": return "Erro"
    conn=get_conn()
    if conn:
        try: cur=conn.cursor(); cur.execute("TRUNCATE inspecoes, cadastros, pedidos_mascaras, justificativas"); conn.commit(); cur.close(); conn.close()
        except: pass
    return "<script>alert('Zerado');window.location='/admin?senha=telemont2026';</script>"

@app_flask.route('/graficos')
def graficos():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper()
    linhas=carregar_inspecoes_lista(filtro_sup, filtro_coord)
    df_nc=[r for r in linhas if r.get('status')=='Não Conforme']
    cont_item=Counter([r.get('item','') for r in df_nc])
    cont_sup=Counter([r.get('supervisor','') for r in df_nc])
    tabela_item="".join([f"<tr><td>{i}</td><td>{q}</td></tr>" for i,q in cont_item.most_common()])
    tabela_sup="".join([f"<tr><td>{s}</td><td>{q}</td></tr>" for s,q in cont_sup.most_common()])
    return f"<html><head><meta charset='utf-8'></head><body><h2>DASHBOARD SUPABASE - Total NC {len(df_nc)}</h2><a href='/base'>BASE</a><table border=1><tr><th>ITEM</th><th>QTD</th></tr>{tabela_item}</table><br><table border=1><tr><th>SUP</th><th>QTD</th></tr>{tabela_sup}</table></body></html>"

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data['resultados']=[]; context.user_data['nao_conforme_lista']=[]
    await update.message.reply_text("INSPECAO - OPERACIONAL\n\nDigite sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6); func=buscar_func(chapa)
    if not func: func=buscar_func(update.message.text.strip())
    if not func: await update.message.reply_text(f"Chapa {chapa} nao existe."); return CHAPA
    if ja_inspecionou(chapa): await update.message.reply_text(f"Chapa {chapa} ja fez inspecao!"); return ConversationHandler.END
    just=get_justificados()
    if chapa in just: await update.message.reply_text(f"Chapa {chapa} JUSTIFICADA"); return ConversationHandler.END
    context.user_data['chapa']=chapa; context.user_data['func']=func
    cad=buscar_cadastro(chapa)
    if cad and cad.get('telefone'):
        context.user_data['telefone']=cad['telefone']
        kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
        await update.message.reply_text(f"{func['nome']}\nVoce e motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return EH_MOTORISTA
    else:
        kb=[[KeyboardButton("Compartilhar telefone", request_contact=True)]]
        await update.message.reply_text(f"{func['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)); return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=re.sub(r'\D','',str(tel_raw))[-11:]
    context.user_data['telefone']=tel
    kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
    await update.message.reply_text(f"Telefone {tel} salvo! Voce e motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return EH_MOTORISTA

async def motorista_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.upper(); eh_mot = "SIM" if "SIM" in texto else "NÃO"; context.user_data['eh_motorista']=eh_mot; func=context.user_data['func']
    d={"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":context.user_data['telefone'],"id_telegram":str(update.effective_user.id),"eh_motorista":eh_mot}
    salvar_cadastro(d)
    if eh_mot=="SIM": context.user_data['itens_filtrados']=ITENS
    else: context.user_data['itens_filtrados']=[i for i in ITENS if i['regra']=="TODOS"]
    context.user_data['item_idx']=0; return await proximo_item(update, context)

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0)
    itens=context.user_data.get('itens_filtrados', ITENS)
    if idx >= len(itens): return await finalizar(update, context)
    item=itens[idx]
    context.user_data['item_atual']=item
    context.user_data['tamanho_atual']=""; context.user_data['data_fab_atual']=""; context.user_data['validade_atual']=""
    if item.get('auto_cone'):
        kb=[[KeyboardButton("Utilitário"), KeyboardButton("Passeio")]]
        await update.message.reply_text(f"{idx+1}/{len(itens)} - {item['nome']}\nTipo:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return CONE_TIPO
    if item.get('auto_mosquetao'):
        kb=[[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")]]
        await update.message.reply_text(f"{idx+1}/{len(itens)} - {item['nome']}\nQtd minima 3! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return TAMANHO
    if item.get('tamanho'):
        await update.message.reply_text(f"{idx+1}/{len(itens)} - {item['nome']}\nDigite TAMANHO:"); return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"{idx+1}/{len(itens)} - {item['nome']}\nDigite DATA FAB DD/MM/AAAA:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text(f"{idx+1}/{len(itens)} - {item['nome']}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def cone_tipo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.strip(); tipo_norm = "Utilitário" if "UTILIT" in tipo.upper() else "Passeio"; context.user_data['cone_tipo'] = tipo_norm
    if tipo_norm == "Utilitário": kb = [[KeyboardButton(str(i)) for i in range(1,6)], [KeyboardButton(str(i)) for i in range(6,11)]]; await update.message.reply_text(f"Utilitario - Minimo 10 cones!\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    else: kb = [[KeyboardButton(str(i)) for i in range(1,6)]]; await update.message.reply_text(f"Passeio - Minimo 5 cones!\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return CONE_QTD

async def cone_qtd_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip(); qtd = int(texto) if texto.isdigit() else 0; tipo = context.user_data.get('cone_tipo','Utilitário')
    status_auto = "Não Conforme" if (tipo=="Utilitário" and qtd<10) or (tipo=="Passeio" and qtd<5) else "Conforme"
    item = context.user_data['item_atual']; res={"item":f"{item['nome']} - {tipo}","tamanho":f"QTD {qtd} - {tipo}","data_fab":"","validade":"","status":status_auto}
    context.user_data['resultados'].append(res)
    if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    await update.message.reply_text(f"{status_auto} CONES {tipo} QTD {qtd} = {status_auto}!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']; texto = update.message.text.strip()
    if item.get('auto_mosquetao'):
        qtd = texto; status_auto = "Não Conforme" if qtd in ["1","2"] else "Conforme"
        res={"item":item['nome'],"tamanho":f"QTD {qtd}","data_fab":"","validade":"","status":status_auto}
        context.user_data['resultados'].append(res)
        if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"{status_auto} MOSQUETAO QTD {qtd} = {status_auto}!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    ok, val = validar_tamanho(texto, item.get('tamanho_tipo',''))
    if not ok: await update.message.reply_text(f"{val}"); return TAMANHO
    context.user_data['tamanho_atual']=val
    if item.get('data_fab'): await update.message.reply_text(f"Tam {val} OK! Agora DATA FAB:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]; await update.message.reply_text(f"Tam {val} OK! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto): await update.message.reply_text("Use DD/MM/AAAA"); return DATA_FAB
    item=context.user_data['item_atual']; validade, vencido = calcular_validade(texto, item.get('validade_anos',5))
    context.user_data['data_fab_atual']=texto; context.user_data['validade_atual']=validade
    if vencido:
        res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":texto,"validade":validade,"status":"Não Conforme"}
        context.user_data['resultados'].append(res); context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"VENCIDO em {validade}! NAO CONFORME AUTOMATICO!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    else: kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]; await update.message.reply_text(f"Validade {validade} - OK\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_raw=update.message.text.strip().upper()
    if "NÃO CONFORME" in texto_raw or texto_raw == "NAO CONFORME" or "NAO CONF" in texto_raw: status="Não Conforme"
    elif "CONFORME" in texto_raw and "NÃO" not in texto_raw: status="Conforme"
    elif "APLICA" in texto_raw: status="Não Aplica"
    else: status="Conforme"
    item=context.user_data['item_atual']
    res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    if status=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    context.user_data['item_idx']+=1
    return await proximo_item(update, context)

async def finalizar(update, context):
    await update.message.reply_text("AGUARDANDO... Salvando no Supabase...")
    chapa=context.user_data['chapa']; func=context.user_data['func']; tel=context.user_data['telefone']; eh_mot=context.user_data['eh_motorista']
    resultados=context.user_data['resultados']; nao_conf=context.user_data['nao_conforme_lista']
    data_hora=datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    conn=get_conn()
    if conn:
        try:
            cur=conn.cursor()
            for r in resultados:
                cur.execute("INSERT INTO inspecoes (data,chapa,nome,cargo,supervisor,coordenador,telefone,eh_motorista,item,tamanho,data_fab,validade,status) VALUES (NOW(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, eh_mot, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status']))
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
        await update.message.reply_text(f"Enviando e-mail para supervisor {func['supervisor']}...")
        enviado, dest = enviar_email_nao_conforme(func['supervisor'], func['coordenador'], chapa, func['nome'], nao_conf, caminho_txt, dados_colab)
    msg=f"FINALIZADA E SALVA NO SUPABASE!\nCHAPA: {chapa}\nNAO CONFORME: {len(nao_conf)}\n\n{txt_conteudo}"
    if enviado: msg+=f"\n\nE-mail: {', '.join(dest)}"
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt))
    kb = ReplyKeyboardMarkup([[KeyboardButton("NOVA INSPECAO - /start")]], resize_keyboard=True)
    await update.message.reply_text("Para nova inspecao:", reply_markup=kb)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("/start - Nova Inspeção")]], resize_keyboard=True)
    await update.message.reply_text("Cancelado! /start", reply_markup=kb); return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    import asyncio
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)], TELEFONE: [MessageHandler(filters.ALL, telefone_step)], EH_MOTORISTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, motorista_step)], TAMANHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tamanho_step)], DATA_FAB: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_fab_step)], STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_step)], CONE_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_tipo_step)], CONE_QTD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_qtd_step)],},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    )
    app.add_handler(conv); app.add_handler(CommandHandler("start", start)); app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
