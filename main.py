import os, threading, csv, datetime, re, uuid, unicodedata, asyncio, io
from collections import Counter, defaultdict
from flask import Flask, send_from_directory, request, Response
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

# SUPABASE
from supabase import create_client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
print(f"SUPABASE: {'ON' if supabase else 'OFF - usando CSV fallback'}")

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_SENHA = os.environ.get("ADMIN_SENHA","telemont2026")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://bot-sesmt-inspecao.onrender.com").rstrip("/")
PASTA_MASC = "/tmp/mascaras"
os.makedirs(PASTA_MASC, exist_ok=True)
BANNER = "banner.jpg"

FUNCIONARIOS = {}
SUPERVISORES_LISTA = set()
COORDENADORES_LISTA = set()

def carregar_funcionarios():
    global FUNCIONARIOS, SUPERVISORES_LISTA, COORDENADORES_LISTA
    FUNCIONARIOS.clear(); SUPERVISORES_LISTA.clear(); COORDENADORES_LISTA.clear()
    if not supabase:
        return
    try:
        # Pega 1000 por vez (Supabase limita)
        all_data = []
        page = 0
        while True:
            res = supabase.table("funcionarios").select("*").range(page*1000, (page+1)*1000-1).execute()
            if not res.data: break
            all_data.extend(res.data)
            if len(res.data) < 1000: break
            page+=1
        for r in all_data:
            chapa_6 = str(r.get('chapa','')).strip().zfill(6)
            if not chapa_6: continue
            sup = str(r.get('supervisor','') or '').strip().upper()
            coord = str(r.get('coordenador','') or r.get('gerente','') or '').strip().upper()
            if sup: SUPERVISORES_LISTA.add(sup)
            if coord: COORDENADORES_LISTA.add(coord)
            FUNCIONARIOS[chapa_6] = {
                "nome": str(r.get('nome','')).strip().upper(),
                "cargo": str(r.get('cargo','')).strip().upper(),
                "admissao": str(r.get('data_admissao','') or r.get('admissao','')),
                "supervisor": sup,
                "coordenador": coord
            }
        print(f"✅ {len(FUNCIONARIOS)} funcionarios do Supabase | {len(SUPERVISORES_LISTA)} supervisores")
    except Exception as e:
        print(f"Erro carregar funcionarios: {e}")

carregar_funcionarios()

def get_justificados():
    just={}
    if supabase:
        try:
            res = supabase.table("justificativas").select("*").execute()
            for r in res.data:
                just[str(r.get('chapa','')).zfill(6)] = r
            return just
        except Exception as e:
            print(f"Erro just: {e}")
    return just

def ja_inspecionou(chapa):
    if supabase:
        try:
            res = supabase.table("inspecoes").select("chapa").eq("chapa", str(chapa).zfill(6)).limit(1).execute()
            return len(res.data) > 0
        except: return False
    return False

def buscar_cadastro(chapa):
    if supabase:
        try:
            res = supabase.table("cadastros").select("*").eq("chapa", str(chapa).zfill(6)).limit(1).execute()
            return res.data[0] if res.data else None
        except: return None
    return None

def salvar_cadastro_supabase(d):
    if not supabase: return
    try:
        supabase.table("cadastros").upsert(d, on_conflict="chapa").execute()
    except Exception as e:
        print(f"Erro salvar cadastro: {e}")

ITENS = [
    {"nome":"CALÇADO DE SEGURANÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2"},
    {"nome":"CAPACETE DE SEGURANÇA", "regra":"TODOS", "tamanho":False, "data_fab":True, "validade_anos":5},
    {"nome":"CARNEIRA/JUGULAR", "regra":"TODOS"},
    {"nome":"ÓCULOS DE SEGURANÇA", "regra":"TODOS"},
    {"nome":"COLETE REFLETIVO", "regra":"TODOS"},
    {"nome":"LUVA DE RASPA", "regra":"TODOS"},
    {"nome":"CINTO DE SEGURANÇA", "regra":"TODOS", "data_fab":True, "validade_anos":5},
    {"nome":"TALABARTE DE POSICIONAMENTO", "regra":"TODOS", "data_fab":True, "validade_anos":5},
    {"nome":"CAPA DE CHUVA", "regra":"TODOS"},
    {"nome":"BOTA DE PVC", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2"},
    {"nome":"PERNEIRA", "regra":"TODOS"},
    {"nome":"ESCADA DUPLA", "regra":"APENAS MOTORISTA"},
    {"nome":"BANDEIROLA", "regra":"APENAS MOTORISTA"},
    {"nome":"CONES DE SINALIZAÇÃO", "regra":"APENAS MOTORISTA", "auto_cone":True},
    {"nome":"TRAVA QUEDAS", "regra":"TODOS", "data_fab":True, "validade_anos":5},
    {"nome":"PROTETOR SOLAR", "regra":"TODOS"},
    {"nome":"GARRA MEIO DE VÃO", "regra":"APENAS MOTORISTA"},
    {"nome":"DETECTOR DE TENSÃO", "regra":"TODOS"},
    {"nome":"VARA DE MANOBRA", "regra":"APENAS MOTORISTA"},
    {"nome":"CHAVE J", "regra":"APENAS MOTORISTA"},
    {"nome":"CHAVE T", "regra":"APENAS MOTORISTA"},
    {"nome":"CORDA 20M", "regra":"APENAS MOTORISTA"},
    {"nome":"FITA AMARRAÇÃO ESCADA", "regra":"APENAS MOTORISTA"},
    {"nome":"FITA DE ANCORAGEM EUREKA", "regra":"APENAS MOTORISTA"},
    {"nome":"FREIO ABS", "regra":"APENAS MOTORISTA"},
    {"nome":"MOSQUETÃO", "regra":"APENAS MOTORISTA", "auto_mosquetao":True},
    {"nome":"CORREIA PARA ESCADA", "regra":"APENAS MOTORISTA"},
    {"nome":"CORDIM PARA ESCADA", "regra":"APENAS MOTORISTA"},
    {"nome":"FITA DE ANCORAGEM 1,5M", "regra":"APENAS MOTORISTA"},
    {"nome":"SACOLA NYLON", "regra":"APENAS MOTORISTA"},
    {"nome":"BOLSA TIRACOLO", "regra":"TODOS"},
    {"nome":"CAMISA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"LETRAS3"},
    {"nome":"CALÇA", "regra":"TODOS", "tamanho":True, "tamanho_tipo":"NUM2"},
    {"nome":"CRACHÁ PADRÃO TELEMONT", "regra":"TODOS"},
    {"nome":"BOLSA DE EPI", "regra":"TODOS"},
]

CHAPA, TELEFONE, EH_MOTORISTA, TAMANHO, DATA_FAB, STATUS, CONE_TIPO, CONE_QTD = range(8)

def buscar_func(chapa):
    return FUNCIONARIOS.get(str(chapa).zfill(6))
def validar_tamanho(v,t):
    v=v.strip().upper()
    if t in ["NUM2","QTD"]:
        return (v.isdigit(), v if v.isdigit() else "Só números!")
    return True, v
def calcular_validade(ds, anos=5):
    try:
        import datetime as dt
        d = dt.datetime.strptime(ds, "%d/%m/%Y")
        venc = d + dt.timedelta(days=anos*365)
        return venc.strftime("%d/%m/%Y"), venc < dt.datetime.now()
    except: return "", False
def gerar_mascara_txt(dados_colab, lista_nc):
    txt = f"""PEDIDO EPI - {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}
CHAPA: {dados_colab['chapa']} - {dados_colab['nome']}
SUP: {dados_colab['supervisor']} - TOTAL NC: {len(lista_nc)}
"""
    for i,r in enumerate(lista_nc,1): txt+=f"{i}. {r['item']}\n"
    nome = f"MASCARA_{dados_colab['chapa']}_{uuid.uuid4().hex[:4]}.txt"
    caminho = os.path.join(PASTA_MASC, nome)
    with open(caminho,"w",encoding="utf-8") as f: f.write(txt)
    return caminho, txt

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return f"BOT ON SUPABASE - <a href='/base'>BASE</a> | <a href='/graficos'>GRAFICOS</a>"

@app_flask.route('/base')
def base():
    filtro_sup = request.args.get('supervisor','').strip().upper()
    filtro_coord = request.args.get('coordenador','').strip().upper()
    feitos=set()
    inspecoes=[]
    try:
        if supabase:
            # Busca inspecoes distintas por chapa
            res = supabase.table("inspecoes").select("chapa").execute()
            for r in res.data: feitos.add(str(r.get('chapa','')).zfill(6))
    except Exception as e: print(e)
    justificados = get_justificados()
    # FILTRO CORRIGIDO
    filtradas={}
    for ch6,dados in FUNCIONARIOS.items():
        if filtro_sup and filtro_sup not in str(dados.get('supervisor','')).upper(): continue
        if filtro_coord and filtro_coord not in str(dados.get('coordenador','')).upper(): continue
        filtradas[ch6]=dados
    por_sup=defaultdict(list)
    for ch6,dados in filtradas.items():
        por_sup[dados.get('supervisor','SEM SUPERVISOR')].append(ch6)
    opt_sup = "<option value=''>-- TODOS --</option>"+"".join([f"<option {'selected' if s==filtro_sup else ''} value='{s}'>{s}</option>" for s in sorted(SUPERVISORES_LISTA)])
    opt_coord = "<option value=''>-- TODOS --</option>"+"".join([f"<option {'selected' if c==filtro_coord else ''} value='{c}'>{c}</option>" for c in sorted(COORDENADORES_LISTA)])
    linhas=""
    for sup,lista in sorted(por_sup.items()):
        total=len(lista); feitos_sup=sum(1 for c in lista if c in feitos); just_sup=sum(1 for c in lista if c in justificados); pend=total-feitos_sup-just_sup; perc=int((feitos_sup+just_sup)/total*100) if total else 0; cor="green" if perc>=100 else "orange" if perc>=50 else "red"
        linhas+=f"<tr><td>{sup}</td><td style='text-align:center'>{total}</td><td style='text-align:center'>{feitos_sup}</td><td style='text-align:center'>{just_sup}</td><td style='text-align:center'><a href='/base/pendentes?supervisor={sup}' style='background:#0F4C8F;color:white;padding:4px 10px;border-radius:10px;text-decoration:none'>{pend}</a></td><td style='background:{cor};color:white;text-align:center'>{perc}%</td></tr>"
    return f"<html><head><meta charset='utf-8'><style>body{{font-family:Arial;padding:15px;background:#f0f2f5}} .card{{background:white;padding:15px;border-radius:10px;margin-bottom:15px}} table{{width:100%;border-collapse:collapse;background:white}} th,td{{border:1px solid #ddd;padding:8px}} th{{background:#0F4C8F;color:white}} .btn{{background:#0F4C8F;color:white;padding:8px 14px;border-radius:5px;text-decoration:none;display:inline-block}}</style></head><body><h2>BASE SUPABASE - {len(filtradas)}/{len(FUNCIONARIOS)}</h2><div class='card'><form>SUP: <select name='supervisor'>{opt_sup}</select> COORD: <select name='coordenador'>{opt_coord}</select> <button class='btn'>Filtrar</button> <a href='/base' class='btn' style='background:#666'>Limpar</a> <a href='/exportar/base?supervisor={filtro_sup}&coordenador={filtro_coord}' class='btn' style='background:#10b981'>📥 Exportar Base</a></form></div><div class='card'><table><tr><th>SUP</th><th>TOTAL</th><th>FEITOS</th><th>JUST</th><th>PEND</th><th>%</th></tr>{linhas or '<tr><td colspan=6>Nenhum</td></tr>'}</table></div></body></html>"

@app_flask.route('/base/pendentes')
def base_pendentes():
    sup_filtro = request.args.get('supervisor','').strip().upper()
    feitos=set()
    try:
        if supabase:
            res = supabase.table("inspecoes").select("chapa").execute()
            for r in res.data: feitos.add(str(r.get('chapa','')).zfill(6))
    except: pass
    justificados = get_justificados()
    pend=[]
    for ch6,dados in FUNCIONARIOS.items():
        if sup_filtro and sup_filtro not in str(dados.get('supervisor','')).upper(): continue
        if ch6 in feitos or ch6 in justificados: continue
        pend.append((ch6,dados))
    linhas="".join([f"<tr><td>{c}</td><td>{d.get('nome')}</td><td>{d.get('cargo')}</td><td><form action='/base/justificar' method='post'><input type='hidden' name='chapa' value='{c}'><input type='hidden' name='supervisor' value='{sup_filtro}'><input name='motivo' required placeholder='Motivo'><button>Justificar</button></form></td></tr>" for c,d in pend])
    return f"<html><body><h2>PENDENTES {sup_filtro} - {len(pend)}</h2><a href='/exportar/pendentes?supervisor={sup_filtro}'>📥 Exportar</a><br><br><table border=1><tr><th>CHAPA</th><th>NOME</th><th>CARGO</th><th>AÇÃO</th></tr>{linhas}</table><br><a href='/base'>Voltar</a></body></html>"

@app_flask.route('/base/justificar', methods=['POST'])
def base_justificar():
    chapa = str(request.form.get('chapa','')).zfill(6)
    motivo = request.form.get('motivo','')
    sup_ret = request.form.get('supervisor','')
    dados = FUNCIONARIOS.get(chapa,{})
    if supabase:
        try:
            supabase.table("justificativas").upsert({"chapa":chapa, "nome":dados.get('nome',''), "supervisor":dados.get('supervisor',''), "coordenador":dados.get('coordenador',''), "motivo":motivo, "data":datetime.datetime.now().isoformat()}, on_conflict="chapa").execute()
        except Exception as e: print(e)
    return f"<script>alert('Justificada {chapa}');window.location='/base/pendentes?supervisor={sup_ret}';</script>"

@app_flask.route('/exportar/<tipo>')
def exportar(tipo):
    output=io.StringIO(); writer=csv.writer(output, delimiter=';')
    filtro_sup=request.args.get('supervisor','').upper()
    filtro_coord=request.args.get('coordenador','').upper()
    if tipo=='base':
        feitos=set()
        if supabase:
            try:
                res=supabase.table("inspecoes").select("chapa").execute()
                for r in res.data: feitos.add(str(r.get('chapa','')).zfill(6))
            except: pass
        just=get_justificados()
        writer.writerow(['CHAPA','NOME','CARGO','SUPERVISOR','COORDENADOR','STATUS'])
        for ch6,dados in FUNCIONARIOS.items():
            if filtro_sup and filtro_sup not in str(dados.get('supervisor','')).upper(): continue
            if filtro_coord and filtro_coord not in str(dados.get('coordenador','')).upper(): continue
            status='FEITO' if ch6 in feitos else 'JUSTIFICADO' if ch6 in just else 'PENDENTE'
            writer.writerow([ch6,dados.get('nome'),dados.get('cargo'),dados.get('supervisor'),dados.get('coordenador'),status])
        nome=f"BASE_{filtro_sup or 'GERAL'}.csv"
    elif tipo=='pendentes':
        feitos=set(); just=get_justificados()
        if supabase:
            res=supabase.table("inspecoes").select("chapa").execute()
            for r in res.data: feitos.add(str(r.get('chapa','')).zfill(6))
        writer.writerow(['CHAPA','NOME','CARGO','SUPERVISOR'])
        for ch6,dados in FUNCIONARIOS.items():
            if filtro_sup and filtro_sup not in str(dados.get('supervisor','')).upper(): continue
            if ch6 in feitos or ch6 in just: continue
            writer.writerow([ch6,dados.get('nome'),dados.get('cargo'),dados.get('supervisor')])
        nome=f"PENDENTES_{filtro_sup}.csv"
    elif tipo=='nao_conforme':
        writer.writerow(['DATA','CHAPA','NOME','SUPERVISOR','ITEM','STATUS'])
        if supabase:
            res=supabase.table("inspecoes").select("*").ilike("status","%NAO CONFORME%").execute()
            for r in res.data:
                writer.writerow([r.get('data'),r.get('chapa'),r.get('nome'),r.get('supervisor'),r.get('item'),r.get('status')])
        nome="NAO_CONFORME.csv"
    else: return "Tipo invalido",400
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":f"attachment; filename={nome}"})

@app_flask.route('/graficos')
def graficos():
    # AGORA LÊ DO SUPABASE - NÃO ZERA MAIS
    linhas=[]
    if supabase:
        try:
            res=supabase.table("inspecoes").select("*").ilike("status","%NAO CONFORME%").execute()
            linhas=res.data
        except Exception as e: print(e)
    total=len(linhas)
    cont_item=Counter([r.get('item','') for r in linhas])
    cont_sup=Counter([r.get('supervisor','') for r in linhas])
    html=f"<html><head><meta charset='utf-8'><style>body{{font-family:Arial;background:#0f172a;color:white;padding:20px}} .card{{background:#1e293b;padding:15px;border-radius:10px;margin:10px 0}}</style></head><body><h1>DASHBOARD SUPABASE - TOTAL NC: {total}</h1><div class='card'><a href='/exportar/nao_conforme' style='background:#10b981;color:white;padding:10px 20px;border-radius:10px;text-decoration:none'>📥 Exportar Não Conformes CSV</a> <a href='/base' style='color:#a78bfa'>BASE</a></div><div class='card'><h3>Por Item</h3>{'<br>'.join([f'{k}: {v}' for k,v in cont_item.most_common()])}</div><div class='card'><h3>Por Supervisor</h3>{'<br>'.join([f'{k}: {v}' for k,v in cont_sup.most_common()])}</div></body></html>"
    return html

# TELEGRAM COM SUPABASE
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear(); context.user_data['resultados']=[]; context.user_data['nao_conforme_lista']=[]
    await update.message.reply_text("🦺 INSPEÇÃO - Digite sua CHAPA:"); return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=str(update.message.text.strip()).zfill(6)
    func=FUNCIONARIOS.get(chapa)
    if not func: await update.message.reply_text(f"❌ Chapa {chapa} não existe no Supabase."); return CHAPA
    if ja_inspecionou(chapa): await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção!"); return ConversationHandler.END
    if chapa in get_justificados(): await update.message.reply_text(f"⛔ Chapa {chapa} justificada!"); return ConversationHandler.END
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
    tel_raw = update.message.contact.phone_number if update.message.contact else update.message.text
    tel = re.sub(r'\D','',str(tel_raw))[-11:]
    if len(tel)<10: await update.message.reply_text("Telefone inválido"); return TELEFONE
    context.user_data['telefone']=tel
    kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
    await update.message.reply_text(f"✅ Tel {tel} salvo! Você é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return EH_MOTORISTA

async def motorista_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    eh_mot="SIM" if "SIM" in update.message.text.upper() else "NÃO"
    context.user_data['eh_motorista']=eh_mot
    func=context.user_data['func']
    salvar_cadastro_supabase({"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":context.user_data['telefone'],"id_telegram":str(update.effective_user.id),"eh_motorista":eh_mot})
    context.user_data['itens_filtrados']=ITENS if eh_mot=="SIM" else [i for i in ITENS if i['regra']=="TODOS"]
    context.user_data['item_idx']=0
    return await proximo_item(update, context)

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0); itens=context.user_data.get('itens_filtrados',ITENS)
    if idx>=len(itens): return await finalizar(update, context)
    item=itens[idx]; context.user_data['item_atual']=item; context.user_data['tamanho_atual']=""; context.user_data['data_fab_atual']=""; context.user_data['validade_atual']=""
    if item.get('auto_cone'):
        kb=[[KeyboardButton("Utilitário"), KeyboardButton("Passeio")]]
        await update.message.reply_text(f"🚧 {idx+1}/{len(itens)} - {item['nome']}\nTipo:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return CONE_TIPO
    if item.get('auto_mosquetao'):
        kb=[[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")]]
        await update.message.reply_text(f"🔗 {item['nome']}\nQtd mínima 3!", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return TAMANHO
    if item.get('tamanho'): await update.message.reply_text(f"📏 {idx+1}/{len(itens)} - {item['nome']}\nTamanho:"); return TAMANHO
    if item.get('data_fab'): await update.message.reply_text(f"📅 {idx+1}/{len(itens)} - {item['nome']}\nData FAB DD/MM/AAAA:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(itens)} - {item['nome']}", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def cone_tipo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cone_tipo']="Utilitário" if "UTILIT" in update.message.text.upper() else "Passeio"
    await update.message.reply_text(f"Mínimo {'10' if context.user_data['cone_tipo']=='Utilitário' else '5'} cones! Qtd:"); return CONE_QTD

async def cone_qtd_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qtd=int(update.message.text) if update.message.text.isdigit() else 0; tipo=context.user_data.get('cone_tipo')
    status_auto="Não Conforme" if (tipo=="Utilitário" and qtd<10) or (tipo=="Passeio" and qtd<5) else "Conforme"
    res={"item":f"{context.user_data['item_atual']['nome']} - {tipo}","tamanho":f"QTD {qtd}","data_fab":"","validade":"","status":status_auto}
    context.user_data['resultados'].append(res)
    if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    context.user_data['item_idx']+=1; return await proximo_item(update, context)

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']
    if item.get('auto_mosquetao'):
        qtd=update.message.text.strip(); status_auto="Não Conforme" if qtd in ["1","2"] else "Conforme"
        res={"item":item['nome'],"tamanho":f"QTD {qtd}","data_fab":"","validade":"","status":status_auto}
        context.user_data['resultados'].append(res)
        if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
        context.user_data['item_idx']+=1; return await proximo_item(update, context)
    context.user_data['tamanho_atual']=update.message.text.strip()
    if item.get('data_fab'): await update.message.reply_text("Data FAB:"); return DATA_FAB
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text("Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto): await update.message.reply_text("Use DD/MM/AAAA"); return DATA_FAB
    validade,vencido=calcular_validade(texto, context.user_data['item_atual'].get('validade_anos',5))
    context.user_data['data_fab_atual']=texto; context.user_data['validade_atual']=validade
    if vencido:
        res={"item":context.user_data['item_atual']['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":texto,"validade":validade,"status":"Não Conforme"}
        context.user_data['resultados'].append(res); context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"⚠️ VENCIDO {validade} - NC!"); context.user_data['item_idx']+=1; return await proximo_item(update, context)
    kb=[[KeyboardButton("Conforme"), KeyboardButton("Não Conforme")]]
    await update.message.reply_text(f"Validade {validade} OK - Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)); return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status="Não Conforme" if "NÃO" in update.message.text.upper() else "Conforme"
    res={"item":context.user_data['item_atual']['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":context.user_data.get('data_fab_atual',''),"validade":context.user_data.get('validade_atual',''),"status":status}
    context.user_data['resultados'].append(res)
    if status=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    context.user_data['item_idx']+=1; return await proximo_item(update, context)

async def finalizar(update, context):
    await update.message.reply_text("⏳ Salvando no Supabase...")
    chapa=context.user_data['chapa']; func=context.user_data['func']; tel=context.user_data['telefone']; eh_mot=context.user_data['eh_motorista']
    resultados=context.user_data['resultados']; nao_conf=context.user_data['nao_conforme_lista']
    dados_colab={"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"eh_motorista":eh_mot}
    # SALVA NO SUPABASE - NÃO APAGA MAIS
    if supabase:
        try:
            rows=[]
            for r in resultados:
                rows.append({"data":datetime.datetime.now().isoformat(),"chapa":chapa,"nome":func['nome'],"cargo":func['cargo'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":tel,"eh_motorista":eh_mot,"item":r['item'],"tamanho":r['tamanho'],"data_fab":r['data_fab'],"validade":r['validade'],"status":r['status']})
            supabase.table("inspecoes").insert(rows).execute()
            if nao_conf:
                caminho,txt=gerar_mascara_txt(dados_colab,nao_conf)
                supabase.table("pedidos_mascaras").insert({"data":datetime.datetime.now().isoformat(),"chapa":chapa,"nome":func['nome'],"telefone":tel,"supervisor":func['supervisor'],"mascara_txt":txt}).execute()
            await update.message.reply_text(f"✅ FINALIZADA NO SUPABASE!\nCHAPA: {chapa}\nNC: {len(nao_conf)}")
        except Exception as e:
            await update.message.reply_text(f"Erro Supabase: {e}")
    else:
        await update.message.reply_text("Supabase OFF")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado /start"); return ConversationHandler.END

# WEBHOOK LOOP FIX
application=None; BOT_LOOP=None
@app_flask.route('/webhook', methods=['POST'])
def webhook():
    global application,BOT_LOOP
    if not application or not BOT_LOOP: return "not ready",503
    try:
        data=request.get_json(force=True)
        upd=Update.de_json(data, application.bot)
        fut=asyncio.run_coroutine_threadsafe(application.process_update(upd), BOT_LOOP)
        fut.result(timeout=20)
    except Exception as e: print(e)
    return "ok"

def start_bot_loop(loop): asyncio.set_event_loop(loop); loop.run_forever()

def run_flask():
    global application,BOT_LOOP
    BOT_LOOP=asyncio.new_event_loop()
    t=threading.Thread(target=start_bot_loop, args=(BOT_LOOP,), daemon=True); t.start()
    async def init_bot():
        global application
        application=Application.builder().token(TOKEN).build()
        conv=ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                CHAPA:[MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)],
                TELEFONE:[MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, telefone_step)],
                EH_MOTORISTA:[MessageHandler(filters.TEXT & ~filters.COMMAND, motorista_step)],
                TAMANHO:[MessageHandler(filters.TEXT & ~filters.COMMAND, tamanho_step)],
                DATA_FAB:[MessageHandler(filters.TEXT & ~filters.COMMAND, data_fab_step)],
                STATUS:[MessageHandler(filters.TEXT & ~filters.COMMAND, status_step)],
                CONE_TIPO:[MessageHandler(filters.TEXT & ~filters.COMMAND, cone_tipo_step)],
                CONE_QTD:[MessageHandler(filters.TEXT & ~filters.COMMAND, cone_qtd_step)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
        )
        application.add_handler(conv)
        await application.initialize(); await application.start()
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
        print(f"✅ WEBHOOK SUPABASE ON: {WEBHOOK_URL}")
    fut=asyncio.run_coroutine_threadsafe(init_bot(), BOT_LOOP); fut.result(timeout=30)
    app_flask.run(host='0.0.0.0', port=int(os.environ.get("PORT",10000)))

def main(): run_flask()
if __name__=="__main__": main()
