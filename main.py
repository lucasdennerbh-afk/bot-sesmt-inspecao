import os, threading, csv, datetime, re, uuid, json, unicodedata, asyncio
from collections import Counter, defaultdict
from flask import Flask, send_from_directory, request, send_file, redirect
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA","telemont2026")
ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros.csv"
ARQ_INS = "inspecoes.csv"
ARQ_PEDIDOS = "pedidos_mascaras.csv"
ARQ_JUST = "justificativas.csv"
PASTA_MASC = "mascaras"
BANNER = "banner.jpg"
ARQ_SUP_EMAIL = "supervisores.csv"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://bot-sesmt-inspecao.onrender.com").rstrip("/")
os.makedirs(PASTA_MASC, exist_ok=True)

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
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("chapa","")).zfill(6) == str(chapa).zfill(6): return True
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
    try:
        with open(ARQ_JUST, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                just[str(r.get('chapa','')).zfill(6)] = r
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
    if not lista_nao_conforme:
        txt += "NENHUM - TODOS CONFORME\n"
    else:
        for i, r in enumerate(lista_nao_conforme, 1):
            txt += f"{i}. {r['item']} - {r.get('status')}\n"
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
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = ", ".join(emails_destino)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
        if caminho_txt and os.path.exists(caminho_txt):
            with open(caminho_txt, "rb") as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(caminho_txt)}")
            msg.attach(part)
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, emails_destino, msg.as_string())
        server.quit()
        return True, emails_destino
    except Exception as e:
        print(f"Erro email: {e}")
        return False, []

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return f"BOT SESMT ON - <a href='/base'>BASE</a> | <a href='/graficos'>GRAFICOS</a> | <a href='/admin?senha={ADMIN_SENHA}'>ADMIN</a>"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)

@app_flask.route('/base')
def base():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper()
    feitos = set()
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                feitos.add(str(r.get('chapa','')).zfill(6))
    except: pass
    justificados = get_justificados()
    por_supervisor = defaultdict(list)
    chapas_unicas = {}
    for chapa_key, dados in FUNCIONARIOS.items():
        ch6 = chapa_key.zfill(6)
        if len(ch6)!=6 or ch6 in chapas_unicas: continue
        chapas_unicas[ch6] = dados
        sup = dados.get('supervisor','SEM SUPERVISOR')
        coord = dados.get('coordenador','SEM COORDENADOR')
        if filtro_sup and filtro_sup not in sup: continue
        if filtro_coord and filtro_coord not in coord: continue
        por_supervisor[sup].append({'chapa':ch6})
    todos_sup = sorted(SUPERVISORES_LISTA)
    todos_coord = sorted(COORDENADORES_LISTA)
    opt_sup = "".join([f"<option value='{s}' {'selected' if s==filtro_sup else ''}>{s}</option>" for s in todos_sup])
    opt_coord = "".join([f"<option value='{c}' {'selected' if c==filtro_coord else ''}>{c}</option>" for c in todos_coord])
    html = f"<html><head><meta charset='utf-8'><title>BASE</title><style>body{{font-family:Arial;padding:15px;background:#f0f2f5}} .card{{background:white;padding:15px;border-radius:10px;margin-bottom:20px}} table{{width:100%;border-collapse:collapse;background:white;font-size:12px}} th,td{{border:1px solid #ddd;padding:7px}} th{{background:#0F4C8F;color:white}}</style></head><body><h2>BASE</h2><div class='card'><form method='get'>SUP: <select name='supervisor'><option>-- TODOS --</option>{opt_sup}</select> COORD: <select name='coordenador'><option>-- TODOS --</option>{opt_coord}</select><button>Filtrar</button></form></div><div class='card'><table><tr><th>SUP</th><th>TOTAL</th><th>FEITOS</th><th>JUST</th><th>PEND</th><th>%</th></tr>"
    for sup, lista in sorted(por_supervisor.items()):
        total=len(lista); feitos_sup=sum(1 for c in lista if c['chapa'] in feitos); just_sup=sum(1 for c in lista if c['chapa'] in justificados); pend=total-feitos_sup-just_sup; perc=int((feitos_sup+just_sup)/total*100) if total else 0; cor="green" if perc>=100 else "orange" if perc>=50 else "red"
        html+=f"<tr><td>{sup}</td><td>{total}</td><td>{feitos_sup}</td><td>{just_sup}</td><td>{pend}</td><td style='background:{cor};color:white'>{perc}%</td></tr>"
    html+="</table></div></body></html>"
    return html

@app_flask.route('/admin')
def admin_panel():
    senha = request.args.get('senha','')
    if senha != ADMIN_SENHA: return f"<form><input type='password' name='senha'><button>Entrar</button></form>"
    return f"<html><body><h2>ADMIN</h2><a href='/base'>BASE</a> | <a href='/graficos'>GRAFICOS</a><br><br><form action='/admin/liberar'><input type='hidden' name='senha' value='{ADMIN_SENHA}'><input name='chapa' placeholder='CHAPA'><button>LIBERAR</button></form></body></html>"

@app_flask.route('/admin/liberar')
def admin_liberar():
    senha = request.args.get('senha','')
    if senha != ADMIN_SENHA: return "Senha inválida"
    chapa = str(request.args.get('chapa','')).zfill(6)
    for arq, fields in [(ARQ_INS, ["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"])]:
        novas=[]
        try:
            with open(arq, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
            with open(arq, "w", newline="", encoding="utf-8") as f:
                w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(novas)
        except: pass
    return f"<script>alert('Liberada {chapa}');window.location='/admin?senha={ADMIN_SENHA}';</script>"

@app_flask.route('/graficos')
def graficos():
    filtro_busca = request.args.get('busca','').strip().upper()
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper() or request.args.get('gerente','').strip().upper()
    filtro_item = request.args.get('item','').strip().upper()
    linhas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sup = str(r.get('supervisor','')).upper()
                coord = str(r.get('coordenador','')).upper()
                item = str(r.get('item','')).upper()
                chapa = str(r.get('chapa','')).upper()
                nome = str(r.get('nome','')).upper()
                if filtro_sup and filtro_sup not in sup: continue
                if filtro_coord and filtro_coord not in coord: continue
                if filtro_item and filtro_item not in item: continue
                if filtro_busca and filtro_busca not in chapa and filtro_busca not in nome: continue
                linhas.append(r)
    except: linhas=[]
    df_nc = [r for r in linhas if 'NÃO CONFORME' in str(r.get('status','')).upper() or 'NAO CONFORME' in str(r.get('status','')).upper()]
    total_nc = len(df_nc)
    cont_item = Counter([r.get('item','').strip() for r in df_nc])
    cont_sup = Counter([r.get('supervisor','').strip() for r in df_nc])
    cont_tam = Counter([r.get('tamanho','').strip() for r in df_nc if r.get('tamanho','').strip()])
    item_critico, qtd_critico = cont_item.most_common(1)[0] if cont_item else ("-", 0)
    sup_critico, qtd_sup_critico = cont_sup.most_common(1)[0] if cont_sup else ("-", 0)
    tam_critico, qtd_tam_critico = cont_tam.most_common(1)[0] if cont_tam else ("-", 0)
    perc_critico = int(qtd_critico/total_nc*100) if total_nc else 0
    todos_sup = sorted(SUPERVISORES_LISTA); todos_coord = sorted(COORDENADORES_LISTA); todos_itens = sorted(set([i['nome'] for i in ITENS]))
    options_sup = "".join([f"<option value='{s}' {'selected' if s==filtro_sup else ''}>{s}</option>" for s in todos_sup])
    options_coord = "".join([f"<option value='{c}' {'selected' if c==filtro_coord else ''}>{c}</option>" for c in todos_coord])
    options_item = "".join([f"<option value='{it}' {'selected' if it==filtro_item else ''}>{it}</option>" for it in todos_itens])
    cont_item_tam = defaultdict(int)
    for r in df_nc:
        key = (r.get('item',''), r.get('tamanho','')); cont_item_tam[key] += 1
    total_por_item = Counter([r.get('item','') for r in df_nc])
    linhas_tabela = ""
    for (item, tam), qtd in sorted(cont_item_tam.items(), key=lambda x: x[1], reverse=True)[:100]:
        total_item = total_por_item.get(item, 1); perc = int(qtd/total_item*100) if total_item else 0
        linhas_tabela += f"<tr><td>{item}</td><td>{tam or '-'}</td><td style='text-align:center'><b>{qtd}</b></td><td style='text-align:center'>{total_item}</td><td style='text-align:center'>{perc}%</td></tr>"
    tabela_sup_soma = "".join([f"<tr><td>{sup}</td><td style='text-align:center;color:#f87171'><b>{qtd}</b></td></tr>" for sup,qtd in cont_sup.most_common()])
    tabela_ranking = "".join([f"<tr><td>{item}</td><td style='text-align:center'><b>{qtd}</b></td><td style='text-align:center'>{int(qtd/total_nc*100) if total_nc else 0}%</td></tr>" for item,qtd in cont_item.most_common()])
    cores = ["#8b5cf6","#06b6d4","#f59e0b","#10b981","#ef4444","#ec4899","#6366f1"]
    barras = ""
    for i, (item, qtd) in enumerate(cont_item.most_common(8)):
        perc = int(qtd/total_nc*100) if total_nc else 0; cor = cores[i % len(cores)]
        barras += f"<div style='margin-bottom:10px'><div style='display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px'><span style='color:#cbd5e1'>{item[:30]}</span><span style='color:white'><b>{perc}%</b> ({qtd})</span></div><div style='background:#1e293b;height:8px;border-radius:10px'><div style='width:{perc}%;background:{cor};height:8px;border-radius:10px'></div></div></div>"
    if not barras:
        barras = f"<div style='display:flex;flex-direction:column;align-items:center;justify-content:center;height:220px'><div style='font-size:42px;font-weight:bold;color:white'>0</div><div style='font-size:10px;color:#94a3b8'>TOTAL NC</div></div>"
    html = f"""<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>DASHBOARD SUPABASE</title><style>*{{box-sizing:border-box}} body{{margin:0;font-family:Arial;background:#0f172a;color:white;padding:20px}} .top{{display:flex;justify-content:space-between;align-items:center}} .top h1{{margin:0;font-size:30px}} .top h1 span{{color:#a78bfa}} .btn{{background:white;color:#0f172a;border:none;padding:9px 20px;border-radius:20px;font-weight:bold;cursor:pointer;text-decoration:none}} .filtros{{background:#1e293b;padding:15px;border-radius:16px;display:flex;gap:12px;margin:15px 0;flex-wrap:wrap;border:1px solid #334155}} .filtros input, .filtros select{{background:#0f172a;border:1px solid #334155;color:#cbd5e1;padding:11px 14px;border-radius:12px;min-width:220px;flex:1}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:15px;margin-bottom:20px}} .card{{padding:18px;border-radius:16px;color:white}} .card p{{margin:0;font-size:10px;opacity:0.8}} .card h2{{margin:8px 0 4px 0;font-size:26px}} .c1{{background:linear-gradient(135deg,#8b5cf6,#6366f1)}} .c2{{background:linear-gradient(135deg,#06b6d4,#3b82f6)}} .c3{{background:linear-gradient(135deg,#f59e0b,#ef4444)}} .c4{{background:linear-gradient(135deg,#10b981,#059669)}} .grid{{display:grid;grid-template-columns:1.2fr 2fr;gap:15px;margin-bottom:15px}} @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}} .box{{background:#1e293b;border-radius:16px;padding:18px;border:1px solid #334155}} .box h3{{margin:0 0 15px 0;font-size:14px}} table{{width:100%;border-collapse:collapse;font-size:12px}} th{{color:#94a3b8;font-size:10px;text-align:left;padding:10px 8px;border-bottom:1px solid #334155}} td{{padding:10px 8px;border-bottom:1px solid #1e293b;color:#cbd5e1}} .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:15px}} @media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}</style></head><body><div class='top'><div><h1>DASHBOARD <span>SUPABASE</span></h1><div style='color:#94a3b8;font-size:13px'>Total NC: <b style='color:white'>{total_nc}</b></div></div><a class='btn' href='/graficos'>Atualizar</a></div><form method='get' class='filtros'><input name='busca' value='{filtro_busca}' placeholder='Chapa ou Nome'><select name='supervisor'><option value=''>Todos Supervisores</option>{options_sup}</select><select name='coordenador'><option value=''>Todos Coordenadores</option>{options_coord}</select><select name='item'><option value=''>Todos Itens</option>{options_item}</select><button class='btn' style='background:#8b5cf6;color:white'>Filtrar</button><a href='/graficos' style='color:#94a3b8;padding:10px;text-decoration:none'>Limpar</a></form><div class='cards'><div class='card c1'><p>TOTAL NC</p><h2>{total_nc}</h2><small>{len(cont_item)} itens</small></div><div class='card c2'><p>ITEM CRÍTICO</p><h2 style='font-size:15px'>{item_critico[:26]}</h2><small>{perc_critico}%</small></div><div class='card c3'><p>SUPERVISOR +NC</p><h2 style='font-size:14px'>{sup_critico[:22]}</h2><small>{qtd_sup_critico}</small></div><div class='card c4'><p>TAMANHO +FALTA</p><h2 style='font-size:15px'>{tam_critico or '-'}</h2><small>{qtd_tam_critico}</small></div></div><div class='grid'><div class='box'><h3>% por Item (Colorido)</h3>{barras}</div><div class='box'><h3>Item | Tamanho | Qtd | Total Item | %</h3><div style='overflow:auto;max-height:360px'><table><tr><th>ITEM</th><th>TAMANHO</th><th>QTD</th><th>TOTAL ITEM</th><th>%</th></tr>{linhas_tabela}<tr style='background:#0f172a;font-weight:bold'><td colspan=2 style='text-align:center'>TOTAL</td><td style='text-align:center'>{total_nc}</td><td style='text-align:center'>{total_nc}</td><td style='text-align:center'>100%</td></tr></table></div></div></div><div class='grid2'><div class='box'><h3>NC por Supervisor - SOMA</h3><table><tr><th>SUPERVISOR</th><th>QTD</th></tr>{tabela_sup_soma}</table></div><div class='box'><h3>Ranking Itens</h3><table><tr><th>ITEM</th><th>QTD</th><th>%</th></tr>{tabela_ranking}</table></div></div><div style='margin-top:20px;text-align:center'><a href='/base' style='color:#a78bfa;margin-right:20px'>BASE</a><a href='/admin?senha={ADMIN_SENHA}' style='color:#94a3b8'>ADMIN</a></div></body></html>"""
    return html

# ===== TELEGRAM =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data['resultados']=[]; context.user_data['nao_conforme_lista']=[]
    try:
        if os.path.exists(BANNER):
            with open(BANNER, "rb") as photo:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="🦺 *INSPEÇÃO - OPERACIONAL*\n\n👇 Digite sua CHAPA:", parse_mode="Markdown")
            return CHAPA
    except: pass
    await update.message.reply_text("🦺 *INSPEÇÃO - OPERACIONAL*\n\nDigite sua CHAPA:"); return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6); func=buscar_func(chapa)
    if not func: func=buscar_func(update.message.text.strip())
    if not func: await update.message.reply_text(f"❌ Chapa {chapa} não existe."); return CHAPA
    if ja_inspecionou(chapa): 
        kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
        await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção!", reply_markup=kb); return ConversationHandler.END
    just = get_justificados()
    if chapa in just:
        kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
        await update.message.reply_text(f"⛔ Chapa {chapa} JUSTIFICADA!", reply_markup=kb); return ConversationHandler.END
    context.user_data['chapa']=chapa; context.user_data['func']=func
    cad=buscar_cadastro(chapa)
    if cad and cad.get('telefone'):
        context.user_data['telefone']=cad['telefone']
        kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
        await update.message.reply_text(f"✅ {func['nome']}\nVocê é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return EH_MOTORISTA
    else:
        kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
        await update.message.reply_text(f"✅ {func['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)); return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tel_raw = ""
        if update.message.contact and update.message.contact.phone_number:
            tel_raw = update.message.contact.phone_number
        else:
            tel_raw = update.message.text or ""
        tel = re.sub(r'\D','',str(tel_raw))
        if len(tel) > 11: tel = tel[-11:]
        if len(tel) < 10:
            await update.message.reply_text(f"❌ Telefone inválido. Digite com DDD, ex: 31999999999")
            return TELEFONE
        context.user_data['telefone']=tel
        kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
        await update.message.reply_text(f"✅ Telefone {tel} salvo!\n\n🚗 Você é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return EH_MOTORISTA
    except Exception as e:
        print(f"Erro telefone_step: {e}")
        await update.message.reply_text("Digite seu telefone com DDD, ex: 31999999999")
        return TELEFONE

async def motorista_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = (update.message.text or "").upper()
        eh_mot = "SIM" if "SIM" in texto else "NÃO"
        context.user_data['eh_motorista']=eh_mot
        func=context.user_data['func']
        d={"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":context.user_data['telefone'],"id_telegram":str(update.effective_user.id),"eh_motorista":eh_mot}
        salvar_cadastro(d)
        if eh_mot=="SIM": context.user_data['itens_filtrados']=ITENS
        else: context.user_data['itens_filtrados']=[i for i in ITENS if i['regra']=="TODOS"]
        context.user_data['item_idx']=0
        await update.message.reply_text(f"✅ {len(context.user_data['itens_filtrados'])} itens - Iniciando...")
        return await proximo_item(update, context)
    except Exception as e:
        print(f"Erro motorista_step: {e}")
        await update.message.reply_text("Clique em SIM ou NÃO novamente")
        return EH_MOTORISTA

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0)
    itens=context.user_data.get('itens_filtrados', ITENS)
    if idx >= len(itens): return await finalizar(update, context)
    item=itens[idx]
    context.user_data['item_atual']=item
    context.user_data['tamanho_atual']=""; context.user_data['data_fab_atual']=""; context.user_data['validade_atual']=""
    if item.get('auto_cone'):
        kb=[[KeyboardButton("Utilitário"), KeyboardButton("Passeio")]]
        await update.message.reply_text(f"🚧 {idx+1}/{len(itens)} - {item['nome']}\nTipo:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return CONE_TIPO
    if item.get('auto_mosquetao'):
        kb=[[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")]]
        await update.message.reply_text(f"🔗 {idx+1}/{len(itens)} - {item['nome']}\nQtd mínima 3! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return TAMANHO
    if item.get('tamanho'):
        await update.message.reply_text(f"📏 {idx+1}/{len(itens)} - {item['nome']}\nDigite TAMANHO:"); return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {idx+1}/{len(itens)} - {item['nome']}\nDigite DATA FAB DD/MM/AAAA:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(itens)} - {item['nome']}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def cone_tipo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.strip(); tipo_norm = "Utilitário" if "UTILIT" in tipo.upper() else "Passeio"; context.user_data['cone_tipo'] = tipo_norm
    if tipo_norm == "Utilitário": kb = [[KeyboardButton(str(i)) for i in range(1,6)], [KeyboardButton(str(i)) for i in range(6,11)]]; await update.message.reply_text(f"🚐 Utilitário - Mínimo 10 cones!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    else: kb = [[KeyboardButton(str(i)) for i in range(1,6)]]; await update.message.reply_text(f"🚗 Passeio - Mínimo 5 cones!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return CONE_QTD

async def cone_qtd_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip(); qtd = int(texto) if texto.isdigit() else 0; tipo = context.user_data.get('cone_tipo','Utilitário')
    status_auto = "Não Conforme" if (tipo=="Utilitário" and qtd<10) or (tipo=="Passeio" and qtd<5) else "Conforme"
    item = context.user_data['item_atual']; res={"item":f"{item['nome']} - {tipo}","tamanho":f"QTD {qtd} - {tipo}","data_fab":"","validade":"","status":status_auto}
    context.user_data['resultados'].append(res)
    if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    await update.message.reply_text(f"{'🔴' if status_auto=='Não Conforme' else '🟢'} {tipo} QTD {qtd} = {status_auto}!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']; texto = update.message.text.strip()
    if item.get('auto_mosquetao'):
        qtd = texto; status_auto = "Não Conforme" if qtd in ["1","2"] else "Conforme"
        res={"item":item['nome'],"tamanho":f"QTD {qtd}","data_fab":"","validade":"","status":status_auto}
        context.user_data['resultados'].append(res)
        if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"{'🔴' if status_auto=='Não Conforme' else '🟢'} MOSQUETÃO QTD {qtd} = {status_auto}!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    ok, val = validar_tamanho(texto, item.get('tamanho_tipo',''))
    if not ok: await update.message.reply_text(f"❌ {val}"); return TAMANHO
    context.user_data['tamanho_atual']=val
    if item.get('data_fab'): await update.message.reply_text(f"Tam {val} OK! Agora DATA FAB:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]; await update.message.reply_text(f"Tam {val} OK! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto): await update.message.reply_text("❌ Use DD/MM/AAAA"); return DATA_FAB
    item=context.user_data['item_atual']; validade, vencido = calcular_validade(texto, item.get('validade_anos',5))
    context.user_data['data_fab_atual']=texto; context.user_data['validade_atual']=validade
    if vencido:
        res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":texto,"validade":validade,"status":"Não Conforme"}
        context.user_data['resultados'].append(res); context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"⚠️ VENCIDO em {validade}! 🔴 NÃO CONFORME!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    else: kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]; await update.message.reply_text(f"Validade {validade} - OK ✅\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_raw=update.message.text.strip().upper()
    if "NÃO CONFORME" in texto_raw or texto_raw == "NAO CONFORME": status="Não Conforme"
    elif "CONFORME" in texto_raw and "NÃO" not in texto_raw: status="Conforme"
    else: status="Conforme"
    item=context.user_data['item_atual']
    res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    if status=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    context.user_data['item_idx']+=1
    return await proximo_item(update, context)

async def finalizar(update, context):
    await update.message.reply_text("⏳ Criando máscara...")
    chapa=context.user_data['chapa']; func=context.user_data['func']; tel=context.user_data['telefone']; eh_mot=context.user_data['eh_motorista']
    resultados=context.user_data['resultados']; nao_conf=context.user_data['nao_conforme_lista']
    data_hora=datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(ARQ_INS, "a", newline="", encoding="utf-8") as f:
        w=csv.writer(f)
        for r in resultados: w.writerow([data_hora, chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, eh_mot, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status']])
    dados_colab={"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"eh_motorista":eh_mot}
    caminho_txt, txt_conteudo = gerar_mascara_txt(dados_colab, nao_conf)
    with open(ARQ_PEDIDOS, "a", newline="", encoding="utf-8") as f: csv.writer(f).writerow([data_hora, chapa, func['nome'], tel, func['supervisor'], txt_conteudo.replace("\n"," | ")])
    enviado=False; dest=[]
    if nao_conf:
        enviado, dest = enviar_email_nao_conforme(func['supervisor'], func['coordenador'], chapa, func['nome'], nao_conf, caminho_txt, dados_colab)
    msg=f"✅ FINALIZADA!\nCHAPA: {chapa}\nNÃO CONFORME: {len(nao_conf)}\n\n{txt_conteudo}"
    if enviado: msg+=f"\n\n📧 E-mail: {', '.join(dest)}"
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        try: await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt))
        except: pass
    kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
    await update.message.reply_text("👇 Nova inspeção:", reply_markup=kb)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("/start - Nova Inspeção")]], resize_keyboard=True)
    await update.message.reply_text("Cancelado! /start", reply_markup=kb); return ConversationHandler.END

# ===== WEBHOOK - CORREÇÃO DEFINITIVA LOOP =====
application = None
BOT_LOOP = None

@app_flask.route('/webhook', methods=['POST'])
def webhook():
    global application, BOT_LOOP
    if not application or not BOT_LOOP:
        return "bot not ready", 503
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), BOT_LOOP)
        future.result(timeout=20)
    except Exception as e:
        print(f"Erro webhook: {e}")
    return "ok"

def start_bot_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def run_flask():
    global application, BOT_LOOP
    
    BOT_LOOP = asyncio.new_event_loop()
    t = threading.Thread(target=start_bot_loop, args=(BOT_LOOP,), daemon=True)
    t.start()

    async def init_bot():
        global application
        application = Application.builder().token(TOKEN).build()
        conv = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)], 
                TELEFONE: [MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, telefone_step)],
                EH_MOTORISTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, motorista_step)], 
                TAMANHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tamanho_step)], 
                DATA_FAB: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_fab_step)], 
                STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_step)], 
                CONE_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_tipo_step)], 
                CONE_QTD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_qtd_step)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
        )
        application.add_handler(conv)
        application.add_handler(CommandHandler("start", start))
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
        print(f"✅ WEBHOOK SETADO: {WEBHOOK_URL}/webhook - LOOP FIX OK")

    fut = asyncio.run_coroutine_threadsafe(init_bot(), BOT_LOOP)
    fut.result(timeout=30)
    
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

def main():
    run_flask()

if __name__=="__main__": 
    main()
