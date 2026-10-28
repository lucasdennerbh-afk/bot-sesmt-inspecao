import os, threading, csv, datetime, re, uuid, json
from flask import Flask, send_from_directory, request, send_file
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("BOT_TOKEN")
ARQ_FUNC = "funcionarios.csv"
ARQ_CAD = "cadastros.csv"
ARQ_INS = "inspecoes.csv"
ARQ_PEDIDOS = "pedidos_mascaras.csv"
PASTA_MASC = "mascaras"
os.makedirs(PASTA_MASC, exist_ok=True)

for arq, head in [(ARQ_CAD, ["chapa","nome","cargo","data_admissao","supervisor","coordenador","telefone","id_telegram"]), (ARQ_INS, ["data","chapa","nome","cargo","supervisor","coordenador","telefone","item","tamanho","data_fab","validade","status","obs"]), (ARQ_PEDIDOS, ["data","chapa","nome","telefone","supervisor","item","tamanho","mascara"])]:
    if not os.path.exists(arq):
        with open(arq, "w", newline="", encoding="utf-8") as f: csv.writer(f).writerow(head)

# ITENS DA SUA PLANILHA
ITENS = [
    {"nome":"CALÇADO DE SEGURANÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CAPACETE DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CARNEIRA/JUGULAR", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"ÓCULOS DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"COLETE REFLETIVO", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"LUVA DE RASPA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CINTO DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "opcoes":["Conforme","Não Aplica"]},
    {"nome":"TALABARTE DE POSICIONAMENTO", "regra":"TODOS", "tamanho":False, "data_fab":True, "opcoes":["Conforme","Não Aplica"]},
    {"nome":"CAPA DE CHUVA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOTA DE PVC", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"PERNEIRA", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"ESCADA DUPLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BANDEIROLA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CONES DE SINALIZAÇÃO", "regra":"APENAS MOTORISTA", "tamanho":True, "tamanho_tipo":"QTD", "label_tamanho":"QUANTIDADE", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"TRAVA QUEDAS", "regra":"TODOS", "tamanho":False, "data_fab":True, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"PROTETOR SOLAR", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"GARRA MEIO DE VÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"DETECTOR DE TENSÃO (CHAVE DE TESTE)", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"VARA DE MANOBRA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CHAVE J", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CHAVE T", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CORDA 20M (LINHA DE VIDA)", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA AMARRAÇÃO ESCADA (CATRACA)", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA DE ANCORAGEM EUREKA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FREIO ABS", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"MOSQUETÃO", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CORREIA PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CORDIM PARA ESCADA", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"FITA DE ANCORAGEM 1,5M (LINHA DE VIDA)", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"SACOLA NYLON (PARA KIT LINHA DE VIDA)", "regra":"APENAS MOTORISTA", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOLSA TIRACOLO", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CAMISA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"LETRAS3", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CALÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2", "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"CRACHÁ PADRÃO TELEMONT", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
    {"nome":"BOLSA DE EPI", "regra":"TODOS", "tamanho":False, "data_fab":False, "opcoes":["Conforme","Não Conforme"]},
]

CHAPA, TELEFONE, ITEM_IDX, TAMANHO, DATA_FAB, STATUS = range(6)

def buscar_func(chapa):
    try:
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline(); f.seek(0)
            delim = ";" if ";" in primeira else ","
            reader = csv.DictReader(f, delimiter=delim)
            reader.fieldnames = [c.strip().lower().replace("\ufeff","").replace(" ","_") for c in reader.fieldnames]
            ch_col = reader.fieldnames[0]
            nome_col = next((c for c in reader.fieldnames if "nome" in c), None)
            cargo_col = next((c for c in reader.fieldnames if "cargo" in c), None)
            adm_col = next((c for c in reader.fieldnames if "admiss" in c or "admis" in c), None)
            sup_col = next((c for c in reader.fieldnames if "superv" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c), None)
            for r in reader:
                if str(r.get(ch_col,"")).strip().zfill(6) == str(chapa).zfill(6):
                    return {"nome": str(r.get(nome_col,"")).upper(), "cargo": str(r.get(cargo_col,"")).upper(), "admissao": str(r.get(adm_col,"")), "supervisor": str(r.get(sup_col,"")).upper(), "coordenador": str(r.get(coord_col,"")).upper()}
    except Exception as e: print(e)
    return None

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
        w=csv.DictWriter(f, fieldnames=["chapa","nome","cargo","data_admissao","supervisor","coordenador","telefone","id_telegram"])
        w.writeheader(); w.writerows(rows)

def validar_tamanho(valor, tipo):
    valor=valor.strip().upper()
    if tipo=="NUM2":
        if not valor.isdigit(): return False, "Só números! Ex: 40"
        if len(valor)>2: return False, "Máximo 2 números!"
        return True, valor
    if tipo=="LETRAS3":
        if not valor.isalpha(): return False, "Só letras! Ex: G, GG, XG"
        if len(valor)>3: return False, "Máximo 3 letras!"
        return True, valor
    if tipo=="QTD":
        if not valor.isdigit(): return False, "Só números!"
        return True, valor
    return True, valor

def calcular_validade(data_str, anos=5):
    try:
        dt = datetime.datetime.strptime(data_str, "%d/%m/%Y")
        venc = dt + datetime.timedelta(days=anos*365)
        return venc.strftime("%d/%m/%Y"), venc < datetime.datetime.now()
    except:
        return "", False

def gerar_mascara_final(dados_colab, resultados):
    try:
        nome_base = f"MASCARA_{dados_colab['chapa']}_{uuid.uuid4().hex[:4]}"
        caminho = os.path.join(PASTA_MASC, f"{nome_base}.png")
        W, H = 900, 700 + len(resultados)*25
        H = min(H, 2000)
        img = Image.new('RGB', (W, H), (238,238,238))
        draw = ImageDraw.Draw(img)
        def bold(x,y,t,c, sz=16):
            try: f=ImageFont.truetype("DejaVuSans-Bold.ttf", sz)
            except: f=ImageFont.load_default()
            draw.text((x,y),t,fill=c,font=f)
        def normal(x,y,t,c, sz=12):
            try: f=ImageFont.truetype("DejaVuSans.ttf", sz)
            except: f=ImageFont.load_default()
            draw.text((x,y),t,fill=c,font=f)
        AZUL=(15,76,143)
        draw.rounded_rectangle([(20,20),(880, H-20)], radius=20, fill=(255,255,255))
        draw.rounded_rectangle([(150,5),(750,60)], radius=20, fill=AZUL)
        bold(200,18,"INSPEÇÃO DE SEGURANÇA - SESMT",(255,255,255),18)
        bold(40,80,f"CHAPA: {dados_colab['chapa']} | NOME: {dados_colab['nome']}",(0,0,0),13)
        bold(40,105,f"CARGO: {dados_colab['cargo']} | ADM: {dados_colab['data_admissao']}",(0,0,0),12)
        bold(40,130,f"SUP: {dados_colab['supervisor']} | COORD: {dados_colab['coordenador']} | TEL: {dados_colab['telefone']}",(0,0,0),11)
        y=170
        for r in resultados:
            cor=(0,150,0) if r['status']=="Conforme" else (200,0,0) if r['status']=="Não Conforme" else (100,100,100)
            txt = f"{r['item']} - {r['status']}"
            if r.get('tamanho'): txt+=f" | Tam: {r['tamanho']}"
            if r.get('data_fab'): txt+=f" | Fab: {r['data_fab']} Venc: {r.get('validade','')}"
            normal(40,y,txt,cor,11)
            y+=22
        bold(40, y+20, f"Assinatura automática: {dados_colab['nome']} - {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", (15,58,110),11)
        img.save(caminho)
        return caminho
    except Exception as e:
        print(e)
        return ""

# FLASK
app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT SESMT ON"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)
@app_flask.route('/base')
def base():
    filtro = request.args.get('chapa','').strip()
    html = f"""
    <html><head><meta charset='utf-8'><title>BASE SESMT</title>
    <style>body{{font-family:Arial;padding:15px;background:#f0f2f5}} table{{width:100%;border-collapse:collapse;background:white;font-size:11px}} th,td{{border:1px solid #ddd;padding:6px;text-align:left}} th{{background:#0F4C8F;color:white}} .btn{{padding:5px 10px;border-radius:4px;text-decoration:none;color:white;font-size:11px}} .del{{background:#dc3545}} .view{{background:#0F4C8F}} .masc{{width:50px;height:50px;object-fit:cover;border:1px solid #0F4C8F}} .masc:hover{{transform:scale(5);z-index:100;position:relative}}</style></head><body>
    <h2>BASE SESMT - INSPEÇÕES</h2>
    <form method='GET'>Filtrar CHAPA: <input name='chapa' value='{filtro}'><button>Buscar</button> <a href='/base'><button type='button'>Limpar</button></a> <a href='/exportar'><button type='button' style='background:green;color:white'>Exportar CSV</button></a> <a href='/pedidos'><button type='button' style='background:orange;color:white'>Ver Pedidos/Máscaras</button></a></form><br>
    <table><tr><th>DATA</th><th>CHAPA</th><th>NOME COMPLETO</th><th>CARGO</th><th>SUPERVISOR</th><th>ITENS</th><th>NÃO CONFORMES</th><th>MÁSCARA</th><th>AÇÃO</th></tr>
    """
    try:
        inspecoes={}
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ch = r.get('chapa','')
                if filtro and filtro.zfill(6) not in ch.zfill(6): continue
                if ch not in inspecoes: inspecoes[ch]={'data':r.get('data',''),'nome':r.get('nome',''),'cargo':r.get('cargo',''),'supervisor':r.get('supervisor',''),'itens':[],'nao_conf':0}
                inspecoes[ch]['itens'].append(r)
                if r.get('status')=='Não Conforme': inspecoes[ch]['nao_conf']+=1
        for ch, d in inspecoes.items():
            masc_path = f""
            # pega mascara mais recente da chapa
            for file in sorted(os.listdir(PASTA_MASC), reverse=True):
                if ch in file: masc_path=file; break
            masc_html = f"<a href='/mascaras/{masc_path}' target=_blank><img class='masc' src='/mascaras/{masc_path}'></a>" if masc_path else "-"
            html+=f"<tr><td>{d['data']}</td><td><b>{ch}</b></td><td>{d['nome']}</td><td>{d['cargo']}</td><td>{d['supervisor']}</td><td>{len(d['itens'])}</td><td style='color:red'><b>{d['nao_conf']}</b></td><td>{masc_html}</td><td><a class='btn view' href='/detalhe/{ch}'>Ver</a> <a class='btn del' href='/apagar/{ch}' onclick=\"return confirm('Apagar chapa {ch}? Vai liberar nova inspeção!')\">Excluir</a></td></tr>"
    except Exception as e:
        html+=f"<tr><td colspan=9>{e}</td></tr>"
    html+="</table></body></html>"
    return html

@app_flask.route('/detalhe/<chapa>')
def detalhe(chapa):
    html=f"<h2>Detalhe Chapa {chapa}</h2><table border=1 cellpadding=6><tr><th>ITEM</th><th>TAMANHO</th><th>FAB</th><th>VALIDADE</th><th>STATUS</th></tr>"
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)==str(chapa).zfill(6):
                    cor="red" if r.get('status')=="Não Conforme" else "green"
                    html+=f"<tr><td>{r.get('item')}</td><td>{r.get('tamanho')}</td><td>{r.get('data_fab')}</td><td>{r.get('validade')}</td><td style='color:{cor}'><b>{r.get('status')}</b></td></tr>"
    except: pass
    html+="</table><br><a href='/base'>Voltar</a>"
    return html

@app_flask.route('/apagar/<chapa>')
def apagar(chapa):
    chapa=str(chapa).zfill(6)
    novas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
        with open(ARQ_INS, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["data","chapa","nome","cargo","supervisor","coordenador","telefone","item","tamanho","data_fab","validade","status","obs"])
            w.writeheader(); w.writerows(novas)
        # apaga mascaras
        for file in os.listdir(PASTA_MASC):
            if chapa in file:
                try: os.remove(os.path.join(PASTA_MASC,file))
                except: pass
    except: pass
    return f"<script>alert('Chapa {chapa} liberada! Pode fazer nova inspeção sem recadastrar.');window.location='/base';</script>"

@app_flask.route('/pedidos')
def pedidos():
    html="<h2>Máscaras de Pedido - Não Conforme</h2><table border=1 cellpadding=6><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>TEL</th><th>SUPERVISOR</th><th>MÁSCARA DE PEDIDO</th></tr>"
    try:
        with open(ARQ_PEDIDOS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                html+=f"<tr><td>{r.get('data')}</td><td>{r.get('chapa')}</td><td>{r.get('nome')}</td><td>{r.get('telefone')}</td><td>{r.get('supervisor')}</td><td><b>{r.get('mascara')}</b></td></tr>"
    except: pass
    html+="</table><br><a href='/base'>Voltar Base</a>"
    return html

@app_flask.route('/exportar')
def exportar(): return send_file(ARQ_INS, as_attachment=True)

def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

# TELEGRAM
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['resultados']=[]
    context.user_data['pedidos']=[]
    await update.message.reply_text("🦺 BOT SESMT - INSPEÇÃO\n\nEnvie sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    func=buscar_func(chapa)
    if not func:
        await update.message.reply_text(f"❌ Chapa {chapa} não existe em funcionarios.csv. Tente outra:")
        return CHAPA
    if ja_inspecionou(chapa):
        await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção!\nNome: {func['nome']}\nPara liberar: vá em /base > Excluir chapa {chapa}\nDepois digite /start novamente.")
        return ConversationHandler.END
    context.user_data['chapa']=chapa
    context.user_data['func']=func
    cad=buscar_cadastro(chapa)
    if cad and cad.get('telefone'):
        context.user_data['telefone']=cad['telefone']
        await update.message.reply_text(f"✅ {func['nome']} - {func['cargo']}\nTelefone já cadastrado: {cad['telefone']}\n\nIniciando inspeção...")
        context.user_data['item_idx']=0
        return await proximo_item(update, context)
    else:
        kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
        await update.message.reply_text(f"✅ Chapa {chapa}\nNome completo: {func['nome']}\nCargo: {func['cargo']}\n\nPrimeiro cadastro: compartilhe seu telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=re.sub(r'\D','',str(tel_raw))[-11:]
    func=context.user_data['func']
    d={"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"id_telegram":str(update.effective_user.id)}
    salvar_cadastro(d)
    context.user_data['telefone']=tel
    await update.message.reply_text(f"Telefone {tel} salvo!\n\nIniciando inspeção...")
    context.user_data['item_idx']=0
    return await proximo_item(update, context)

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0)
    func=context.user_data['func']
    # pula itens de motorista se não for motorista
    while idx < len(ITENS):
        item=ITENS[idx]
        if item['regra']=="APENAS MOTORISTA" and "MOTORISTA" not in func['cargo']:
            idx+=1
            continue
        break
    if idx >= len(ITENS):
        return await finalizar(update, context)
    context.user_data['item_idx']=idx
    item=ITENS[idx]
    context.user_data['item_atual']=item
    context.user_data['tamanho_atual']=""
    context.user_data['data_fab_atual']=""
    # se precisa tamanho, pede primeiro
    if item.get('tamanho'):
        label=item.get('label_tamanho','TAMANHO')
        tipo=item.get('tamanho_tipo','')
        msg=f"📏 {idx+1}/{len(ITENS)} - {item['nome']}\n\nRegra: {label} - "
        if tipo=="NUM2": msg+="Máximo 2 números (ex: 40)"
        elif tipo=="LETRAS3": msg+="Máximo 3 letras (ex: G, GG)"
        elif tipo=="QTD": msg+="Quantidade (só números)"
        msg+=f"\n\nDigite o {label}:"
        await update.message.reply_text(msg)
        return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {idx+1}/{len(ITENS)} - {item['nome']}\n\nDigite a DATA DE FABRICAÇÃO (DD/MM/AAAA):")
        return DATA_FAB
    # direto status
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(ITENS)} - {item['nome']}\n\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']
    ok, val = validar_tamanho(update.message.text.strip(), item.get('tamanho_tipo',''))
    if not ok:
        await update.message.reply_text(f"❌ {val}\nTente novamente:")
        return TAMANHO
    context.user_data['tamanho_atual']=val
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {item['nome']} - Tamanho {val} OK!\n\nAgora digite DATA DE FABRICAÇÃO (DD/MM/AAAA):")
        return DATA_FAB
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"Tamanho {val} OK! Selecione status:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    # valida data DD/MM/AAAA
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto):
        await update.message.reply_text("❌ Data inválida! Use DD/MM/AAAA ex: 10/05/2023")
        return DATA_FAB
    context.user_data['data_fab_atual']=texto
    item=context.user_data['item_atual']
    validade, vencido = calcular_validade(texto, item.get('validade_anos',5))
    context.user_data['validade_atual']=validade
    context.user_data['vencido']=vencido
    if vencido:
        await update.message.reply_text(f"⚠️ ATENÇÃO! Vencido em {validade} (5 anos após fabricação)\n")
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"Data {texto} OK! Validade: {validade}\n\nSelecione status:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status=update.message.text.strip()
    item=context.user_data['item_atual']
    if status not in item['opcoes']:
        await update.message.reply_text(f"Selecione uma opção válida: {', '.join(item['opcoes'])}")
        return STATUS
    # salva resultado
    res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    # se Não Conforme -> gera mascara pedido
    if status=="Não Conforme":
        chapa=context.user_data['chapa']
        func=context.user_data['func']
        tel=context.user_data['telefone']
        mascara_pedido = f"{item['nome']} | TAM: {res['tamanho'] or 'N/A'} | {func['nome']} | CHAPA {chapa} | TEL {tel} | SUP {func['supervisor']}"
        context.user_data['pedidos'].append(mascara_pedido)
        # salva em csv pedidos
        with open(ARQ_PEDIDOS, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([datetime.datetime.now().strftime("%d/%m/%Y %H:%M"), chapa, func['nome'], tel, func['supervisor'], item['nome'], res['tamanho'], mascara_pedido])
        await update.message.reply_text(f"🔴 Gerada máscara de pedido:\n{mascara_pedido}")
    # proximo
    context.user_data['item_idx']+=1
    context.user_data['tamanho_atual']=""
    context.user_data['data_fab_atual']=""
    context.user_data['validade_atual']=""
    return await proximo_item(update, context)

async def finalizar(update, context):
    chapa=context.user_data['chapa']
    func=context.user_data['func']
    tel=context.user_data['telefone']
    resultados=context.user_data['resultados']
    data_hora=datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    # salva inspecoes.csv
    with open(ARQ_INS, "a", newline="", encoding="utf-8") as f:
        w=csv.writer(f)
        for r in resultados:
            w.writerow([data_hora, chapa, func['nome'], func['cargo'], func['supervisor'], func['coordenador'], tel, r['item'], r['tamanho'], r['data_fab'], r['validade'], r['status'], ""])
    # gera mascara final
    dados_colab={"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel}
    masc_path=gerar_mascara_final(dados_colab, resultados)
    # monta resumo
    nao_conf=[r for r in resultados if r['status']=="Não Conforme"]
    msg=f"✅ INSPEÇÃO FINALIZADA!\n\nCHAPA: {chapa}\nNOME COMPLETO: {func['nome']}\nCARGO: {func['cargo']}\nSUP: {func['supervisor']}\n\nTotal itens: {len(resultados)}\nNão Conformes: {len(nao_conf)}\n\n"
    if nao_conf:
        msg+="📋 MÁSCARAS DE PEDIDO GERADAS:\n"
        for m in context.user_data['pedidos']:
            msg+=f"- {m}\n"
    msg+=f"\nAssinatura automática: {func['nome']} em {data_hora}\n\nVeja em /base e /pedidos"
    await update.message.reply_text(msg)
    if masc_path and os.path.exists(masc_path):
        with open(masc_path, "rb") as photo:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption=f"MÁSCARA FINAL - {func['nome']} - CHAPA {chapa}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado. /start para reiniciar")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    import asyncio
    try: asyncio.set_event_loop(asyncio.new_event_loop())
    except: pass
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)],
            TELEFONE: [MessageHandler(filters.ALL, telefone_step)],
            TAMANHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tamanho_step)],
            DATA_FAB: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_fab_step)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
