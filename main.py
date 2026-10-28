import os, threading, csv, datetime, re, uuid
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
BANNER = "banner.jpg"
os.makedirs(PASTA_MASC, exist_ok=True)

FUNCIONARIOS = {}
def carregar_funcionarios():
    global FUNCIONARIOS
    try:
        with open(ARQ_FUNC, encoding="utf-8-sig") as f:
            primeira = f.readline()
            delim = ";" if ";" in primeira else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delim)
            reader.fieldnames = [c.strip().lower().replace("\ufeff","").replace(" ","_") for c in reader.fieldnames]
            ch_col = reader.fieldnames[0]
            nome_col = next((c for c in reader.fieldnames if "nome" in c), None)
            cargo_col = next((c for c in reader.fieldnames if "cargo" in c), None)
            adm_col = next((c for c in reader.fieldnames if "admiss" in c), None)
            sup_col = next((c for c in reader.fieldnames if "superv" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c), None)
            for r in reader:
                try:
                    chapa_raw = str(r.get(ch_col,"")).strip()
                    if not chapa_raw: continue
                    chapa_6 = chapa_raw.zfill(6)
                    FUNCIONARIOS[chapa_6] = {
                        "nome": str(r.get(nome_col,"")).strip().upper(),
                        "cargo": str(r.get(cargo_col,"")).strip().upper(),
                        "admissao": str(r.get(adm_col,"")).strip(),
                        "supervisor": str(r.get(sup_col,"")).strip().upper(),
                        "coordenador": str(r.get(coord_col,"")).strip().upper()
                    }
                    FUNCIONARIOS[chapa_raw] = FUNCIONARIOS[chapa_6]
                except: continue
            print(f"FUNCIONARIOS CARREGADOS")
    except Exception as e:
        print(f"ERRO: {e}")
carregar_funcionarios()

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

CHAPA, TELEFONE, EH_MOTORISTA, TAMANHO, DATA_FAB, STATUS = range(6)

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
    if tipo=="NUM2":
        if not valor.isdigit(): return False, "Só números! Ex: 40"
        if len(valor)>2: return False, "Máximo 2 números!"
        return True, valor
    if tipo=="LETRAS3":
        if not valor.isalpha(): return False, "Só letras! Ex: G, GG"
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
    except: return "", False

def gerar_mascara_txt(dados_colab, lista_nao_conforme):
    txt = f"""PEDIDO DE EPI - NÃO CONFORME

CHAPA: {dados_colab['chapa']}
NOME: {dados_colab['nome']}
TELEFONE: {dados_colab['telefone']}

ITENS NÃO CONFORME:
"""
    if not lista_nao_conforme:
        txt += "NENHUM - Todos conforme\n"
    else:
        for r in lista_nao_conforme:
            linha = f"- {r['item']}"
            if r.get('tamanho'): linha += f" | TAMANHO: {r['tamanho']}"
            txt += linha + "\n"
    txt += f"""

SUPERVISOR: {dados_colab['supervisor']}
DATA: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}

"""
    nome_arq = f"MASCARA_{dados_colab['chapa']}_{uuid.uuid4().hex[:4]}.txt"
    caminho = os.path.join(PASTA_MASC, nome_arq)
    with open(caminho, "w", encoding="utf-8") as f: f.write(txt)
    return caminho, txt

def gerar_mascara_final_img(dados_colab, resultados, txt_mascara):
    try:
        nome_base = f"MASCARA_{dados_colab['chapa']}_{uuid.uuid4().hex[:4]}.png"
        caminho = os.path.join(PASTA_MASC, nome_base)
        W, H = 900, 800 + len(resultados)*22
        H = min(H, 2200)
        img = Image.new('RGB', (W, H), (238,238,238))
        draw = ImageDraw.Draw(img)
        def bold(x,y,t,c, sz=14):
            try: f=ImageFont.truetype("DejaVuSans-Bold.ttf", sz)
            except: f=ImageFont.load_default()
            draw.text((x,y),t,fill=c,font=f)
        def normal(x,y,t,c, sz=11):
            try: f=ImageFont.truetype("DejaVuSans.ttf", sz)
            except: f=ImageFont.load_default()
            draw.text((x,y),t,fill=c,font=f)
        AZUL=(15,76,143)
        draw.rounded_rectangle([(20,20),(880, H-20)], radius=20, fill=(255,255,255))
        draw.rounded_rectangle([(150,5),(750,60)], radius=20, fill=AZUL)
        bold(200,18,"INSPEÇÃO SESMT - MÁSCARA FINAL",(255,255,255),15)
        bold(40,80,f"CHAPA: {dados_colab['chapa']} | NOME: {dados_colab['nome']}",(0,0,0),12)
        bold(40,105,f"TEL: {dados_colab['telefone']} | MOTORISTA: {dados_colab['eh_motorista']}",(0,0,0),11)
        bold(40,125,f"SUP: {dados_colab['supervisor']}",(0,0,0),10)
        y=160
        bold(40,y,"MÁSCARA TXT - NÃO CONFORME:",AZUL,12); y+=20
        for linha in txt_mascara.split("\n")[:12]:
            normal(40,y,linha,(0,0,0),9); y+=14
        y+=10
        bold(40,y,"DETALHE:",AZUL,11); y+=20
        for r in resultados:
            cor=(0,150,0) if r['status']=="Conforme" else (200,0,0)
            txt = f"{r['item']} - {r['status']}"
            if r.get('tamanho'): txt+=f" | Tam: {r['tamanho']}"
            normal(40,y,txt,cor,10); y+=18
        bold(40, y+15, f"Assinatura: {dados_colab['nome']}", AZUL,10)
        img.save(caminho)
        return caminho
    except: return ""

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return f"BOT SESMT ON - {len(FUNCIONARIOS)//2} funcionarios"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)
@app_flask.route('/base')
def base():
    filtro = request.args.get('chapa','').strip()
    html = f"<html><head><meta charset='utf-8'><title>BASE</title><style>body{{font-family:Arial;padding:15px}} table{{width:100%;border-collapse:collapse;background:white;font-size:11px}} th,td{{border:1px solid #ddd;padding:6px}} th{{background:#0F4C8F;color:white}} .btn{{padding:5px 10px;border-radius:4px;text-decoration:none;color:white}} .del{{background:#dc3545}} .view{{background:#0F4C8F}}</style></head><body><h2>BASE SESMT</h2><form>CHAPA: <input name='chapa' value='{filtro}'><button>Buscar</button></form><table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>TEL</th><th>MOT</th><th>SUP</th><th>NÃO CONF</th><th>AÇÃO</th></tr>"
    try:
        inspecoes={}
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ch = r.get('chapa','')
                if filtro and filtro.zfill(6) not in ch.zfill(6): continue
                if ch not in inspecoes: inspecoes[ch]={'data':r.get('data',''),'nome':r.get('nome',''),'telefone':r.get('telefone',''),'eh_motorista':r.get('eh_motorista',''),'supervisor':r.get('supervisor',''),'nao_conf':0}
                if r.get('status')=='Não Conforme': inspecoes[ch]['nao_conf']+=1
        for ch, d in inspecoes.items():
            html+=f"<tr><td>{d['data']}</td><td>{ch}</td><td>{d['nome']}</td><td>{d['telefone']}</td><td>{d['eh_motorista']}</td><td>{d['supervisor']}</td><td style='color:red'><b>{d['nao_conf']}</b></td><td><a class='view' href='/detalhe/{ch}'>Ver</a> <a class='del' href='/apagar/{ch}'>Excluir</a></td></tr>"
    except Exception as e: html+=str(e)
    html+="</table><br><a href='/pedidos'>Ver Máscaras TXT</a></body></html>"
    return html
@app_flask.route('/detalhe/<chapa>')
def detalhe(chapa):
    html=f"<h2>Detalhe {chapa}</h2><table border=1><tr><th>ITEM</th><th>TAM</th><th>STATUS</th></tr>"
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)==str(chapa).zfill(6):
                    html+=f"<tr><td>{r.get('item')}</td><td>{r.get('tamanho')}</td><td>{r.get('status')}</td></tr>"
    except: pass
    html+="</table><a href='/base'>Voltar</a>"; return html
@app_flask.route('/apagar/<chapa>')
def apagar(chapa):
    chapa=str(chapa).zfill(6)
    novas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)!=chapa: novas.append(r)
        with open(ARQ_INS, "w", newline="", encoding="utf-8") as f:
            w=csv.DictWriter(f, fieldnames=["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"])
            w.writeheader(); w.writerows(novas)
    except: pass
    return f"<script>alert('Chapa {chapa} liberada!');window.location='/base';</script>"
@app_flask.route('/pedidos')
def pedidos():
    html="<h2>Máscaras TXT</h2><a href='/base'>Voltar</a><br>"
    try:
        for file in sorted(os.listdir(PASTA_MASC), reverse=True):
            if file.endswith('.txt'):
                with open(os.path.join(PASTA_MASC,file), encoding="utf-8") as txtf: conteudo=txtf.read()
                html+=f"<div style='background:#fffbe6;padding:10px;margin:5px;border:1px solid #ddd'><b>{file}</b><br><a href='/mascaras/{file}' target=_blank>Baixar TXT</a><pre>{conteudo}</pre></div>"
    except: pass
    return html
@app_flask.route('/exportar')
def exportar(): return send_file(ARQ_INS, as_attachment=True)
def run_flask(): app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['resultados']=[]; context.user_data['nao_conforme_lista']=[]
    try:
        if os.path.exists(BANNER):
            with open(BANNER, "rb") as photo:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="🦺 *INSPEÇÃO DE SEGURANÇA - OPERACIONAL*\n\n⚠️ Sistema oficial SESMT!\n🔧 Segurança • Conformidade • Prevenção\n\n👇 Digite sua CHAPA para começar.", parse_mode="Markdown")
        else:
            await update.message.reply_text("🦺 INSPEÇÃO DE SEGURANÇA - OPERACIONAL\nDigite sua CHAPA:")
    except:
        await update.message.reply_text("🦺 INSPEÇÃO DE SEGURANÇA - OPERACIONAL\nDigite sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    func=buscar_func(chapa)
    if not func: func=buscar_func(update.message.text.strip())
    if not func:
        await update.message.reply_text(f"❌ Chapa {chapa} não existe. Tente outra:")
        return CHAPA
    if ja_inspecionou(chapa):
        await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção! Nome: {func['nome']}\nPara liberar: /base > Excluir")
        return ConversationHandler.END
    context.user_data['chapa']=chapa; context.user_data['func']=func
    cad=buscar_cadastro(chapa)
    if cad and cad.get('telefone'):
        context.user_data['telefone']=cad['telefone']
        kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
        await update.message.reply_text(f"✅ {func['nome']}\nTelefone: {cad['telefone']}\n\nVocê é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return EH_MOTORISTA
    else:
        kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
        await update.message.reply_text(f"✅ {func['nome']}\nPrimeiro cadastro: compartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=re.sub(r'\D','',str(tel_raw))[-11:]
    context.user_data['telefone']=tel
    kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
    await update.message.reply_text(f"Telefone {tel} salvo!\n\nVocê é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return EH_MOTORISTA

async def motorista_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.upper()
    eh_mot = "SIM" if "SIM" in texto else "NÃO"
    context.user_data['eh_motorista']=eh_mot
    func=context.user_data['func']
    d={"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":context.user_data['telefone'],"id_telegram":str(update.effective_user.id),"eh_motorista":eh_mot}
    salvar_cadastro(d)
    await update.message.reply_text(f"✅ Motorista: {eh_mot}\nIniciando inspeção...")
    if eh_mot=="SIM": context.user_data['itens_filtrados']=ITENS
    else: context.user_data['itens_filtrados']=[i for i in ITENS if i['regra']=="TODOS"]
    context.user_data['item_idx']=0
    await update.message.reply_text(f"Serão {len(context.user_data['itens_filtrados'])} itens para você!")
    return await proximo_item(update, context)

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0)
    itens=context.user_data.get('itens_filtrados', ITENS)
    if idx >= len(itens): return await finalizar(update, context)
    item=itens[idx]
    context.user_data['item_atual']=item; context.user_data['tamanho_atual']=""; context.user_data['data_fab_atual']=""
    if item.get('tamanho'):
        label=item.get('label_tamanho','TAMANHO')
        await update.message.reply_text(f"📏 {idx+1}/{len(itens)} - {item['nome']}\nDigite o {label}:")
        return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {idx+1}/{len(itens)} - {item['nome']}\nDigite DATA FABRICAÇÃO DD/MM/AAAA:")
        return DATA_FAB
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(itens)} - {item['nome']}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']
    ok, val = validar_tamanho(update.message.text.strip(), item.get('tamanho_tipo',''))
    if not ok:
        await update.message.reply_text(f"❌ {val}\nTente novamente:")
        return TAMANHO
    context.user_data['tamanho_atual']=val
    if item.get('data_fab'):
        await update.message.reply_text(f"Tamanho {val} OK! Agora DATA FABRICAÇÃO DD/MM/AAAA:")
        return DATA_FAB
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"Tamanho {val} OK! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto):
        await update.message.reply_text("❌ Use DD/MM/AAAA ex: 10/05/2023")
        return DATA_FAB
    context.user_data['data_fab_atual']=texto
    validade, vencido = calcular_validade(texto, item.get('validade_anos',5) if (item:=context.user_data['item_atual']) else 5)
    context.user_data['validade_atual']=validade
    if vencido: await update.message.reply_text(f"⚠️ Vencido em {validade}!")
    kb=[[KeyboardButton(o) for o in context.user_data['item_atual']['opcoes']]]
    await update.message.reply_text(f"Data {texto} Validade: {validade}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status=update.message.text.strip()
    item=context.user_data['item_atual']
    if status not in item['opcoes']:
        await update.message.reply_text(f"Selecione: {', '.join(item['opcoes'])}")
        return STATUS
    res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    if status=="Não Conforme":
        context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"🔴 Anotado como Não Conforme! Vai pra máscara final.")
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
    caminho_img = gerar_mascara_final_img(dados_colab, resultados, txt_conteudo)
    with open(ARQ_PEDIDOS, "a", newline="", encoding="utf-8") as f: csv.writer(f).writerow([data_hora, chapa, func['nome'], tel, func['supervisor'], txt_conteudo.replace("\n"," | ")])
    msg=f"✅ FINALIZADA!\n\nCHAPA: {chapa}\nNOME: {func['nome']}\nTEL: {tel}\nMOT: {eh_mot}\n\nTotal: {len(resultados)} | Não Conf: {len(nao_conf)}\n\n📋 MÁSCARA TXT:\n\n{txt_conteudo}"
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt), caption="📄 MÁSCARA TXT")
    if caminho_img and os.path.exists(caminho_img):
        with open(caminho_img, "rb") as photo: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption=f"MÁSCARA FINAL - {func['nome']}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado /start")
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
            EH_MOTORISTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, motorista_step)],
            TAMANHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, tamanho_step)],
            DATA_FAB: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_fab_step)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, status_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
