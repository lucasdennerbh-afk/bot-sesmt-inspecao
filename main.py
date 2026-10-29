import os, threading, csv, datetime, re, uuid, json, unicodedata
from collections import Counter, defaultdict
from flask import Flask, send_from_directory, request, send_file
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros.csv"
ARQ_INS = "inspecoes.csv"
ARQ_PEDIDOS = "pedidos_mascaras.csv"
PASTA_MASC = "mascaras"
BANNER = "banner.jpg"
ARQ_SUP_EMAIL = "supervisores.csv"
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
                if sup and email:
                    EMAILS_SUP[sup] = email
    except: pass
carregar_emails_sup()

for arq, head in [(ARQ_CAD, ["chapa","nome","cargo","data_admissao","supervisor","coordenador","telefone","id_telegram","eh_motorista"]), (ARQ_INS, ["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"]), (ARQ_PEDIDOS, ["data","chapa","nome","telefone","supervisor","mascara_txt"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(head)

ITENS = [
    {"nome":"CALÇADO DE SEGURANÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CAPACETE DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CARNEIRA/JUGULAR", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"ÓCULOS DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"COLETE REFLETIVO", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"LUVA DE RASPA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CINTO DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5, "opcoes":["Conforme","Não Aplica"]},
    {"nome":"TALABARTE DE POSICIONAMENTO", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5, "opcoes":["Conforme","Não Aplica"]},
    {"nome":"CAPA DE CHUVA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOTA DE PVC", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"PERNEIRA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"ESCADA DUPLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BANDEIROLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CONES DE SINALIZAÇÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"], "auto_cone":True},
    {"nome":"TRAVA QUEDAS", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"PROTETOR SOLAR", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"GARRA MEIO DE VÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"DETECTOR DE TENSÃO", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"VARA DE MANOBRA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CHAVE J", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CHAVE T", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CORDA 20M", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA AMARRAÇÃO ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA DE ANCORAGEM EUREKA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FREIO ABS", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"MOSQUETÃO", "regra":"APENAS MOTORISTA", "tamanho":True, "tamanho_tipo":"QTD", "label_tamanho":"QUANTIDADE (1, 2 ou 3)", "data_fab":False, "opcoes":["1","2","3"], "auto_mosquetao":True},
    {"nome":"CORREIA PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CORDIM PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA DE ANCORAGEM 1,5M", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"SACOLA NYLON", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOLSA TIRACOLO", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CAMISA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"LETRAS3", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CALÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CRACHÁ PADRÃO TELEMONT", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOLSA DE EPI", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
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

def gerar_mascara_txt(dados_colab, lista_nao_conforme):
    txt = f"""PEDIDO DE EPI - NÃO CONFORME
CHAPA: {dados_colab['chapa']}
NOME: {dados_colab['nome']}
TEL: {dados_colab['telefone']}
SUPERVISOR: {dados_colab['supervisor']}
COORDENADOR: {dados_colab.get('coordenador','')}
DATA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}

ITENS NÃO CONFORME:
"""
    if not lista_nao_conforme: txt += "NENHUM\n"
    else:
        for r in lista_nao_conforme:
            txt += f"- {r['item']} | {r.get('tamanho','')} | {r.get('data_fab','')}\n"
    nome_arq = f"MASCARA_{dados_colab['chapa']}_{uuid.uuid4().hex[:4]}.txt"
    caminho = os.path.join(PASTA_MASC, nome_arq)
    with open(caminho, "w", encoding="utf-8") as f: f.write(txt)
    return caminho, txt

def gerar_excel_completo(caminho="/tmp/sesmt_completo.xlsx", filtro_supervisor="", filtro_gerente=""):
    try:
        import pandas as pd
    except: return None
    linhas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sup = str(r.get('supervisor','')).upper()
                coord = str(r.get('coordenador','')).upper()
                if filtro_supervisor and filtro_supervisor not in sup: continue
                if filtro_gerente and filtro_gerente not in coord: continue
                linhas.append(r)
    except: linhas=[]
    if not linhas: return None
    df = pd.DataFrame(linhas)
    df_nc = df[df['status']=='Não Conforme']
    resumo = df_nc.groupby('item').size().reset_index(name='QTD_NAO_CONFORME').sort_values('QTD_NAO_CONFORME', ascending=False)
    resumo_sup = df_nc.groupby(['supervisor','item']).size().reset_index(name='QTD')
    resumo_coord = df_nc.groupby(['coordenador','item']).size().reset_index(name='QTD')
    with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
        resumo.to_excel(writer, sheet_name='RESUMO_NAO_CONFORME', index=False)
        df.to_excel(writer, sheet_name='DETALHADO_FILTRADO', index=False)
        df_nc.to_excel(writer, sheet_name='SO_NAO_CONFORME', index=False)
        resumo_sup.to_excel(writer, sheet_name='POR_SUPERVISOR', index=False)
        resumo_coord.to_excel(writer, sheet_name='POR_GERENTE', index=False)
    return caminho

def enviar_email_nao_conforme(supervisor_nome, coordenador_nome, chapa, nome_colab, lista_nao_conforme, caminho_txt, dados_colab):
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        emails_destino = []
        email_sup = EMAILS_SUP.get(supervisor_nome.upper()) if supervisor_nome else None
        email_coord = EMAILS_SUP.get(coordenador_nome.upper()) if coordenador_nome else None
        if email_sup: emails_destino.append(email_sup)
        if email_coord and email_coord not in emails_destino: emails_destino.append(email_coord)
        if not emails_destino: return False, []
        EMAIL_USER = os.environ.get("EMAIL_USER", "botsesmt@gmail.com")
        EMAIL_PASS = os.environ.get("EMAIL_PASS", "tcepcskwinxlfnsk")
        SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        assunto = f"INSPEÇÃO NÃO CONFORME - CHAPA {chapa} - {nome_colab}"
        corpo = f"""Segue os itens não conforme de chapa {chapa} - {nome_colab}

CHAPA: {chapa}
NOME: {nome_colab}
SUPERVISOR: {supervisor_nome}
COORDENADOR: {coordenador_nome}
TEL: {dados_colab.get('telefone','')}
DATA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}

ITENS NÃO CONFORME ({len(lista_nao_conforme)}):
"""
        for r in lista_nao_conforme:
            corpo += f"- {r['item']} | TAM: {r.get('tamanho','')} | FAB: {r.get('data_fab','')}\n"
        corpo += "\nMÁSCARA EM ANEXO.\n\nSESMT - Telemont\n"
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = ", ".join(emails_destino)
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
        if caminho_txt and os.path.exists(caminho_txt):
            with open(caminho_txt, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(caminho_txt)}")
            msg.attach(part)
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
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
def home(): return f"BOT SESMT ON - <a href='/base'>BASE</a> | <a href='/excel'>EXCEL</a> | <a href='/graficos'>GRAFICOS</a>"

@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)

@app_flask.route('/excel')
def excel_route():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_ger = request.args.get('gerente','').strip().upper()
    caminho = gerar_excel_completo(filtro_supervisor=filtro_sup, filtro_gerente=filtro_ger)
    if not caminho or not os.path.exists(caminho): return "Sem dados para este filtro"
    nome = f"SESMT_{filtro_sup or 'TODOS'}_{filtro_ger or 'TODOS'}_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}.xlsx"
    return send_file(caminho, as_attachment=True, download_name=nome)

@app_flask.route('/graficos')
def graficos():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_ger = request.args.get('gerente','').strip().upper()
    linhas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sup = str(r.get('supervisor','')).upper()
                coord = str(r.get('coordenador','')).upper()
                if filtro_sup and filtro_sup not in sup: continue
                if filtro_ger and filtro_ger not in coord: continue
                linhas.append(r)
    except: linhas=[]
    df_nc = [r for r in linhas if str(r.get('status','')).strip() == 'Não Conforme']
    todos_sup = sorted(SUPERVISORES_LISTA)
    todos_ger = sorted(COORDENADORES_LISTA)
    options_sup = "".join([f"<option value='{s}' {'selected' if s==filtro_sup else ''}>{s}</option>" for s in todos_sup])
    options_ger = "".join([f"<option value='{g}' {'selected' if g==filtro_ger else ''}>{g}</option>" for g in todos_ger])
    cont_item = Counter([r.get('item','').strip() for r in df_nc if r.get('item')])
    cont_sup = Counter([r.get('supervisor','').strip() for r in df_nc if r.get('supervisor')])
    cont_ger = Counter([r.get('coordenador','').strip() for r in df_nc if r.get('coordenador')])
    cont_sup_item = defaultdict(Counter)
    for r in df_nc:
        sup = r.get('supervisor','').strip()
        item = r.get('item','').strip()
        if sup and item: cont_sup_item[sup][item] += 1
    top_itens = cont_item.most_common(15)
    labels_itens = [x[0] for x in top_itens]
    values_itens = [int(x[1]) for x in top_itens]
    top_sup = cont_sup.most_common(15)
    labels_sup = [x[0] for x in top_sup]
    values_sup = [int(x[1]) for x in top_sup]
    top_ger = cont_ger.most_common(15)
    labels_ger = [x[0] for x in top_ger]
    values_ger = [int(x[1]) for x in top_ger]
    tabela_sup = "".join([f"<tr><td><b>{sup}</b></td><td>{EMAILS_SUP.get(sup,'')}</td><td style='color:red;text-align:center'><b>{qtd}</b></td></tr>" for sup,qtd in cont_sup.most_common()])
    tabela_sup_detalhada = "".join([f"<tr><td>{sup}</td><td>{item}</td><td style='color:red;text-align:center'><b>{qtd}</b></td></tr>" for sup, counter in cont_sup_item.items() for item,qtd in counter.most_common()])
    cont_item_tam = defaultdict(Counter)
    for r in df_nc:
        cont_item_tam[r.get('item','')][r.get('tamanho','')] += 1
    tabela_item_tamanho = "".join([f"<tr><td>{item}</td><td><b>{tam}</b></td><td style='color:red;text-align:center'><b>{qtd}</b></td></tr>" for item, c in cont_item_tam.items() for tam,qtd in c.most_common() if tam])
    filtro_txt = f"FILTRO: Sup={filtro_sup or 'TODOS'} | Ger={filtro_ger or 'TODOS'} - Total: {len(df_nc)}" if filtro_sup or filtro_ger else f"SEM FILTRO - Total: {len(df_nc)}"
    html = f"""
    <html><head><meta charset='utf-8'><title>GRÁFICOS</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>
    <style>body{{font-family:Arial;padding:20px;background:#f0f2f5}} .card{{background:white;padding:20px;border-radius:10px;margin-bottom:20px}} h2{{color:#0F4C8F}} table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:8px;font-size:13px}} th{{background:#0F4C8F;color:white}} .chart-wrap{{height:400px}} select{{padding:8px;min-width:280px}} .btn{{padding:8px 14px;border-radius:5px;color:white;background:#0F4C8F;text-decoration:none}} .btn-green{{background:green}}</style></head><body>
    <h2>📊 DASHBOARD SESMT</h2><a href='/base'>BASE</a> | <a href='/emails'>EMAILS</a>
    <div class='card' style='background:#e8f0fe;border:2px solid #0F4C8F'>
        <form method='get' style='display:flex;gap:15px;flex-wrap:wrap'><div><b>SUPERVISOR:</b><br><select name='supervisor'><option value=''>-- TODOS --</option>{options_sup}</select></div><div><b>GERENTE:</b><br><select name='gerente'><option value=''>-- TODOS --</option>{options_ger}</select></div><div><br><button class='btn'>🔍 FILTRAR</button> <a href='/graficos' class='btn' style='background:#6c757d'>Limpar</a> <a href='/excel?supervisor={filtro_sup}&gerente={filtro_ger}' class='btn btn-green'>📥 EXCEL FILTRO</a></div></form><div style='margin-top:10px;color:#0F4C8F;font-weight:bold'>{filtro_txt}</div>
    </div>
    <div style='display:flex;gap:20px;flex-wrap:wrap'><div class='card' style='flex:2;min-width:500px'><h3>Por Item</h3><div class='chart-wrap'><canvas id='chartItens'></canvas></div></div><div class='card' style='flex:1;min-width:400px'><h3>Por Supervisor</h3><div class='chart-wrap'><canvas id='chartSup'></canvas></div></div><div class='card' style='flex:1;min-width:400px'><h3>Por Gerente</h3><div class='chart-wrap'><canvas id='chartGer'></canvas></div></div></div>
    <div style='display:flex;gap:20px;flex-wrap:wrap'><div class='card' style='flex:1'><h3>👷 SOMA POR SUPERVISOR</h3><table><tr><th>SUP</th><th>EMAIL</th><th>QTD</th></tr>{tabela_sup}</table><br><table><tr><th>SUP</th><th>ITEM</th><th>QTD</th></tr>{tabela_sup_detalhada}</table></div><div class='card' style='flex:1'><h3>📦 Item + Tamanho</h3><table><tr><th>ITEM</th><th>TAM</th><th>QTD</th></tr>{tabela_item_tamanho}</table></div></div>
    <script>
    const labelsItens = {json.dumps(labels_itens)}; const valuesItens = {json.dumps(values_itens)};
    const labelsSup = {json.dumps(labels_sup)}; const valuesSup = {json.dumps(values_sup)};
    const labelsGer = {json.dumps(labels_ger)}; const valuesGer = {json.dumps(values_ger)};
    new Chart(document.getElementById('chartItens'), {{type:'bar', data:{{labels:labelsItens, datasets:[{{data:valuesItens, backgroundColor:'#0F4C8F'}}]}}, options:{{indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}, datalabels:{{anchor:'end', align:'end', color:'#000', font:{{weight:'bold', size:14}}}} }}, scales:{{x:{{beginAtZero:true}}}} }}, plugins:[ChartDataLabels]}});
    new Chart(document.getElementById('chartSup'), {{type:'bar', data:{{labels:labelsSup, datasets:[{{data:valuesSup, backgroundColor:'#FFCC00'}}]}}, options:{{indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}, datalabels:{{anchor:'end', align:'end', color:'#000', font:{{weight:'bold', size:14}}}} }}, scales:{{x:{{beginAtZero:true}}}} }}, plugins:[ChartDataLabels]}});
    new Chart(document.getElementById('chartGer'), {{type:'bar', data:{{labels:labelsGer, datasets:[{{data:valuesGer, backgroundColor:'#28a745'}}]}}, options:{{indexAxis:'y', responsive:true, maintainAspectRatio:false, plugins:{{legend:{{display:false}}, datalabels:{{anchor:'end', align:'end', color:'#000', font:{{weight:'bold', size:14}}}} }}, scales:{{x:{{beginAtZero:true}}}} }}, plugins:[ChartDataLabels]}});
    </script></body></html>"""
    return html

@app_flask.route('/emails')
def ver_emails():
    html="<h2>Emails</h2><a href='/graficos'>Voltar</a><br><br><table border=1 cellpadding=8><tr><th>NOME</th><th>EMAIL</th></tr>"
    for n,e in sorted(EMAILS_SUP.items()): html+=f"<tr><td>{n}</td><td>{e}</td></tr>"
    html+="</table>"
    return html

@app_flask.route('/base')
def base():
    html = "<html><head><meta charset='utf-8'><title>BASE</title><style>body{font-family:Arial;padding:15px;background:#f0f2f5} table{width:100%;border-collapse:collapse;background:white;font-size:11px} th,td{border:1px solid #ddd;padding:6px} th{background:#0F4C8F;color:white} .btn{padding:5px 10px;border-radius:4px;color:white;text-decoration:none}</style></head><body><h2>BASE</h2><a class='btn' style='background:green' href='/excel'>EXCEL</a> <a class='btn' style='background:#fd7e14' href='/graficos'>GRAFICOS</a><br><br><table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>SUP</th><th>COORD</th><th>NC</th><th>AÇÃO</th></tr>"
    try:
        inspecoes={}
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ch=r.get('chapa','')
                if ch not in inspecoes: inspecoes[ch]={'data':r.get('data',''),'nome':r.get('nome',''),'supervisor':r.get('supervisor',''),'coordenador':r.get('coordenador',''),'nao_conf':0}
                if r.get('status')=='Não Conforme': inspecoes[ch]['nao_conf']+=1
        for ch,d in inspecoes.items():
            html+=f"<tr><td>{d['data']}</td><td><b>{ch}</b></td><td>{d['nome']}</td><td>{d['supervisor']}</td><td>{d['coordenador']}</td><td style='color:red'><b>{d['nao_conf']}</b></td><td><a class='btn' style='background:#0F4C8F' href='/detalhe/{ch}'>Ver</a> <a class='btn' style='background:#dc3545' href='/apagar/{ch}'>Excluir</a></td></tr>"
    except Exception as e: html+=str(e)
    html+="</table></body></html>"
    return html

@app_flask.route('/detalhe/<chapa>')
def detalhe(chapa):
    html=f"<h2>Detalhe {chapa}</h2><a href='/base'>Voltar</a><br><table border=1 cellpadding=6><tr><th>ITEM</th><th>TAM</th><th>FAB</th><th>STATUS</th></tr>"
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)==str(chapa).zfill(6):
                    cor="red" if r.get('status')=="Não Conforme" else "green"
                    html+=f"<tr><td>{r.get('item')}</td><td>{r.get('tamanho')}</td><td>{r.get('data_fab')}</td><td style='color:{cor}'><b>{r.get('status')}</b></td></tr>"
    except: pass
    html+="</table>"; return html

@app_flask.route('/apagar/<chapa>')
def apagar(chapa):
    chapa=str(chapa).zfill(6); novas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
        with open(ARQ_INS, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"])
            w.writeheader(); w.writerows(novas)
    except: pass
    return f"<script>alert('Chapa {chapa} liberada!');window.location='/base';</script>"

@app_flask.route('/exportar')
def exportar(): return send_file(ARQ_INS, as_attachment=True)
def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data['resultados']=[]; context.user_data['nao_conforme_lista']=[]
    try:
        if os.path.exists(BANNER):
            with open(BANNER, "rb") as photo:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="🦺 *INSPEÇÃO DE SEGURANÇA - OPERACIONAL*\n\n👇 Digite sua CHAPA:", parse_mode="Markdown")
            return CHAPA
    except: pass
    await update.message.reply_text("🦺 *INSPEÇÃO DE SEGURANÇA - OPERACIONAL*\n\nDigite sua CHAPA:"); return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6); func=buscar_func(chapa)
    if not func: func=buscar_func(update.message.text.strip())
    if not func: await update.message.reply_text(f"❌ Chapa {chapa} não existe."); return CHAPA
    if ja_inspecionou(chapa): kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True); await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção!", reply_markup=kb); return ConversationHandler.END
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
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text; tel=re.sub(r'\D','',str(tel_raw))[-11:]; context.user_data['telefone']=tel
    kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
    await update.message.reply_text(f"Telefone {tel} salvo! Você é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return EH_MOTORISTA

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
    if idx >= len(itens):
        return await finalizar(update, context)
    item=itens[idx]
    context.user_data['item_atual']=item
    context.user_data['tamanho_atual']=""
    context.user_data['data_fab_atual']=""
    context.user_data['validade_atual']=""
    if item.get('auto_cone'):
        kb=[[KeyboardButton("Utilitário"), KeyboardButton("Passeio")]]
        await update.message.reply_text(f"🚧 {idx+1}/{len(itens)} - {item['nome']}\nTipo:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return CONE_TIPO
    if item.get('auto_mosquetao'):
        kb=[[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")]]
        await update.message.reply_text(f"🔗 {idx+1}/{len(itens)} - {item['nome']}\nQuantidade mínima 3! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return TAMANHO
    if item.get('tamanho'):
        await update.message.reply_text(f"📏 {idx+1}/{len(itens)} - {item['nome']}\nDigite {item.get('label_tamanho','TAMANHO')}:")
        return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {idx+1}/{len(itens)} - {item['nome']}\nDigite DATA FAB DD/MM/AAAA:")
        return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(itens)} - {item['nome']}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def cone_tipo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.strip(); tipo_norm = "Utilitário" if "UTILIT" in tipo.upper() else "Passeio"; context.user_data['cone_tipo'] = tipo_norm
    if tipo_norm == "Utilitário": kb = [[KeyboardButton(str(i)) for i in range(1,6)], [KeyboardButton(str(i)) for i in range(6,11)]]; await update.message.reply_text(f"🚐 Utilitário - Mínimo 10 cones!\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    else: kb = [[KeyboardButton(str(i)) for i in range(1,6)]]; await update.message.reply_text(f"🚗 Passeio - Mínimo 5 cones!\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return CONE_QTD

async def cone_qtd_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip(); qtd = int(texto) if texto.isdigit() else 0; tipo = context.user_data.get('cone_tipo','Utilitário')
    status_auto = "Não Conforme" if (tipo=="Utilitário" and qtd<10) or (tipo=="Passeio" and qtd<5) else "Conforme"
    item = context.user_data['item_atual']; res={"item":f"{item['nome']} - {tipo}","tamanho":f"QTD {qtd} - {tipo}","data_fab":"","validade":"","status":status_auto}
    context.user_data['resultados'].append(res)
    if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    await update.message.reply_text(f"{'🔴' if status_auto=='Não Conforme' else '🟢'} CONES {tipo} QTD {qtd} = {status_auto}!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)

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
        await update.message.reply_text(f"⚠️ VENCIDO em {validade}! 🔴 NÃO CONFORME AUTOMÁTICO!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    else: kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]; await update.message.reply_text(f"📅 Validade {validade} - OK ✅\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_raw=update.message.text.strip()
    texto = texto_raw.upper()
    if "NÃO" in texto or "NAO" in texto:
        status="Não Conforme" if "CONFORME" in texto else "Não Conforme"
        if "NÃO APLICA" in texto or "NAO APLICA" in texto:
            status="Não Aplica"
    elif "CONFORME" in texto:
        status="Conforme"
    else:
        # aceita qualquer coisa pra não travar
        status="Conforme" if "C" in texto else "Não Conforme"
        if texto_raw.lower() in ["conforme","não conforme","nao conforme","não aplica","nao aplica","conforme "," conforme"]:
            status = texto_raw.capitalize() if "Não" not in texto_raw else "Não Conforme"

    # Normalização final
    if "NÃO CONFORME" in texto or texto.strip().upper() == "NAO CONFORME":
        status="Não Conforme"
    elif "CONFORME" in texto and "NÃO" not in texto:
        status="Conforme"
    elif "APLICA" in texto:
        status="Não Aplica"

    item=context.user_data['item_atual']
    res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    if status=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    context.user_data['item_idx']+=1
    return await proximo_item(update, context)

async def finalizar(update, context):
    chapa=context.user_data['chapa']; func=context.user_data['func']; tel=context.user_data['telefone']; eh_mot=context.user_data['eh_motorista']
    resultados=context.user_data['resultados']; nao_conf=context.user_data['nao_conforme_lista']
    data_hora=datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(ARQ_INS, "a", newline="", encoding="utf-8") as f:
        w=csv.writer(f)
        for r in resultados: w.writerow([data_hora, chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, eh_mot, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status']])
    dados_colab={"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"eh_motorista":eh_mot}
    caminho_txt, txt_conteudo = gerar_mascara_txt(dados_colab, nao_conf)
    with open(ARQ_PEDIDOS, "a", newline="", encoding="utf-8") as f: csv.writer(f).writerow([data_hora, chapa, func['nome'], tel, func['supervisor'], txt_conteudo.replace("\n"," | ")])
    enviado=False; dest=[]
    if nao_conf:
        enviado, dest = enviar_email_nao_conforme(func['supervisor'], func['coordenador'], chapa, func['nome'], nao_conf, caminho_txt, dados_colab)
    msg=f"✅ FINALIZADA!\n\nCHAPA: {chapa}\nNÃO CONF: {len(nao_conf)}\n\n📋 MÁSCARA:\n{txt_conteudo}"
    if enviado: msg+=f"\n\n📧 E-mail enviado para: {', '.join(dest)}"
    elif nao_conf: msg+=f"\n\n⚠️ Email não configurado no Render."
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt), caption="📄 MÁSCARA TXT")
    kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
    await update.message.reply_text("👇 Para nova inspeção clique:", reply_markup=kb)
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
