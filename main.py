import os, threading, csv, datetime, re, uuid, json
from collections import Counter, defaultdict
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
            sup_col = next((c for c in reader.fieldnames if "superv" in c), None)
            coord_col = next((c for c in reader.fieldnames if "coord" in c), None)
            cargo_col = next((c for c in reader.fieldnames if "cargo" in c), None)
            adm_col = next((c for c in reader.fieldnames if "admiss" in c), None)
            for r in reader:
                try:
                    chapa_raw = str(r.get(ch_col,"")).strip()
                    if not chapa_raw: continue
                    chapa_6 = chapa_raw.zfill(6)
                    FUNCIONARIOS[chapa_6] = {"nome": str(r.get(nome_col,"")).strip().upper(),"cargo": str(r.get(cargo_col,"")).strip().upper(),"admissao": str(r.get(adm_col,"")).strip(),"supervisor": str(r.get(sup_col,"")).strip().upper(),"coordenador": str(r.get(coord_col,"")).strip().upper()}
                    FUNCIONARIOS[chapa_raw] = FUNCIONARIOS[chapa_6]
                except: continue
    except: pass
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
    if tipo=="NUM2":
        if not valor.isdigit(): return False, "Só números!"
        return True, valor
    if tipo=="LETRAS3":
        if not valor.isalpha(): return False, "Só letras!"
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
TEL: {dados_colab['telefone']}
SUPERVISOR: {dados_colab['supervisor']}
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

# ================= NOVO: GERAR EXCEL COMPLETO =================
def gerar_excel_completo(caminho="/tmp/sesmt_completo.xlsx"):
    try:
        import pandas as pd
        from openpyxl import Workbook
    except:
        return None
    
    linhas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                linhas.append(r)
    except: linhas=[]
    
    if not linhas:
        return None
    
    # DataFrame
    import pandas as pd
    df = pd.DataFrame(linhas)
    
    # --- ABA 1: RESUMO NÃO CONFORME ---
    df_nc = df[df['status']=='Não Conforme']
    resumo = df_nc.groupby('item').size().reset_index(name='QTD_NAO_CONFORME')
    resumo = resumo.sort_values('QTD_NAO_CONFORME', ascending=False)
    
    # --- ABA 2: TAMANHOS SEPARADOS ---
    def extrair_tamanho_qtd(valor):
        # valor tipo "QTD 2 - Utilitário" ou "40" ou "G"
        tamanho=""
        quantidade=""
        tipo_veiculo=""
        if not valor: return tamanho, quantidade, tipo_veiculo
        v=str(valor).upper()
        # pega numero
        import re
        nums=re.findall(r'\d+', v)
        if "QTD" in v and nums:
            quantidade=nums[0]
            tamanho=valor
        elif "UTILIT" in v or "PASSEIO" in v:
            tipo_veiculo="Utilitário" if "UTILIT" in v else "Passeio"
            if nums: quantidade=nums[0]
            tamanho=valor
        else:
            tamanho=valor
            if nums: quantidade=nums[0] if "QTD" not in v else nums[0]
        return tamanho, quantidade, tipo_veiculo
    
    df_tam = df.copy()
    df_tam[['TAMANHO_COL','QUANTIDADE_COL','TIPO_VEICULO']] = df_tam['tamanho'].apply(lambda x: pd.Series(extrair_tamanho_qtd(x)))
    
    # --- ABA 3: RESUMO POR SUPERVISOR ---
    resumo_sup = df_nc.groupby(['supervisor','item']).size().reset_index(name='QTD')
    
    with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
        resumo.to_excel(writer, sheet_name='RESUMO_NAO_CONFORME', index=False)
        df.to_excel(writer, sheet_name='DETALHADO_COMPLETO', index=False)
        df_tam.to_excel(writer, sheet_name='TAMANHOS_SEPARADOS', index=False)
        resumo_sup.to_excel(writer, sheet_name='POR_SUPERVISOR', index=False)
        df_nc.to_excel(writer, sheet_name='SO_NAO_CONFORME', index=False)
    return caminho

app_flask = Flask(__name__)
@app_flask.route('/')
def home(): return "BOT SESMT ON - <a href='/base'>BASE</a> | <a href='/excel'>EXCEL COMPLETO</a> | <a href='/graficos'>GRAFICOS</a>"
@app_flask.route('/mascaras/<path:filename>')
def masc(filename): return send_from_directory(PASTA_MASC, filename)

@app_flask.route('/excel')
def excel_route():
    caminho = gerar_excel_completo()
    if not caminho or not os.path.exists(caminho):
        return "Sem dados ainda ou falta biblioteca openpyxl/pandas no requirements.txt"
    return send_file(caminho, as_attachment=True, download_name=f"SESMT_COMPLETO_{datetime.datetime.now().strftime('%d%m%Y_%H%M')}.xlsx")

@app_flask.route('/graficos')
def graficos():
    linhas=[]
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                linhas.append(r)
    except: linhas=[]
    
    df_nc = [r for r in linhas if r.get('status')=='Não Conforme']
    cont_item = Counter([r.get('item','') for r in df_nc])
    cont_sup = Counter([r.get('supervisor','') for r in df_nc])
    cont_tam = Counter([r.get('tamanho','') for r in df_nc if r.get('tamanho')])
    
    # Top 15 itens
    top_itens = cont_item.most_common(15)
    labels_itens = [x[0] for x in top_itens]
    values_itens = [x[1] for x in top_itens]
    
    labels_sup = list(cont_sup.keys())[:10]
    values_sup = list(cont_sup.values())[:10]
    
    html = f"""
    <html><head><meta charset='utf-8'><title>GRÁFICOS SESMT</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>body{{font-family:Arial;padding:20px;background:#f0f2f5}} .card{{background:white;padding:20px;border-radius:10px;margin-bottom:20px;box-shadow:0 2px 5px #ccc}} h2{{color:#0F4C8F}}</style></head><body>
    <h2>📊 DASHBOARD SESMT - NÃO CONFORME</h2>
    <a href='/base'>BASE</a> | <a href='/excel'>BAIXAR EXCEL</a> | <a href='/graficos'>ATUALIZAR</a>
    <div style='display:flex;gap:20px;flex-wrap:wrap'>
    <div class='card' style='flex:2;min-width:400px'><h3>Total Não Conforme por Item (Top 15)</h3><canvas id='chartItens'></canvas></div>
    <div class='card' style='flex:1;min-width:300px'><h3>Por Supervisor</h3><canvas id='chartSup'></canvas></div>
    </div>
    <div class='card'><h3>Resumo</h3>
    <p>Total inspeções: {len(linhas)} registros | Total Não Conforme: {len(df_nc)}</p>
    <p><b>Itens com tamanho/quantidade separados no Excel na aba TAMANHOS_SEPARADOS</b></p>
    <table border=1 cellpadding=5><tr><th>Item</th><th>Qtd Não Conforme</th></tr>
    {''.join([f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k,v in cont_item.most_common()])}
    </table>
    </div>
    <script>
    const ctx1 = document.getElementById('chartItens').getContext('2d');
    new Chart(ctx1, {{type:'bar', data:{{labels:{json.dumps(labels_itens)}, datasets:[{{label:'Qtd Não Conforme', data:{json.dumps(values_itens)}, backgroundColor:'#0F4C8F'}}]}}, options:{{indexAxis:'y'}}}});
    const ctx2 = document.getElementById('chartSup').getContext('2d');
    new Chart(ctx2, {{type:'pie', data:{{labels:{json.dumps(labels_sup)}, datasets:[{{data:{json.dumps(values_sup)}, backgroundColor:['#0F4C8F','#FFCC00','#28a745','#dc3545','#fd7e14','#6f42c1','#20c997','#6610f2','#e83e8c','#17a2b8']}}]}}}});
    </script>
    </body></html>
    """
    return html

@app_flask.route('/base')
def base():
    filtro_chapa = request.args.get('chapa','').strip()
    filtro_sup = request.args.get('supervisor','').strip().upper()
    html = f"<html><head><meta charset='utf-8'><title>BASE SESMT</title><style>body{{font-family:Arial;padding:15px;background:#f0f2f5}} table{{width:100%;border-collapse:collapse;background:white;font-size:11px}} th,td{{border:1px solid #ddd;padding:6px}} th{{background:#0F4C8F;color:white}} .btn{{padding:5px 10px;border-radius:4px;text-decoration:none;color:white;font-size:11px}} .del{{background:#dc3545}} .view{{background:#0F4C8F}} .excel{{background:green}} .graf{{background:#fd7e14}}</style></head><body><h2>BASE SESMT</h2><a class='btn excel' href='/excel'>📥 BAIXAR EXCEL COMPLETO (com abas)</a> <a class='btn graf' href='/graficos'>📊 VER GRÁFICOS</a><br><br><form>CHAPA: <input name='chapa' value='{filtro_chapa}'> SUPERVISOR: <input name='supervisor' value='{filtro_sup}'><button>Buscar</button> <a href='/base'>Limpar</a> <a href='/exportar'>CSV Simples</a></form><br><table><tr><th>DATA</th><th>CHAPA</th><th>NOME</th><th>SUPERVISOR</th><th>NÃO CONF</th><th>AÇÃO</th></tr>"
    try:
        inspecoes={}
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ch = r.get('chapa',''); sup = r.get('supervisor','').upper()
                if filtro_chapa and filtro_chapa.zfill(6) not in ch.zfill(6): continue
                if filtro_sup and filtro_sup not in sup: continue
                if ch not in inspecoes: inspecoes[ch]={'data':r.get('data',''),'nome':r.get('nome',''),'supervisor':r.get('supervisor',''),'nao_conf':0}
                if r.get('status')=='Não Conforme': inspecoes[ch]['nao_conf']+=1
        for ch, d in inspecoes.items():
            html+=f"<tr><td>{d['data']}</td><td><b>{ch}</b></td><td>{d['nome']}</td><td>{d['supervisor']}</td><td style='color:red'><b>{d['nao_conf']}</b></td><td><a class='btn view' href='/detalhe/{ch}'>Ver</a> <a class='btn del' href='/apagar/{ch}'>Excluir</a></td></tr>"
    except Exception as e: html+=str(e)
    html+="</table></body></html>"
    return html

@app_flask.route('/detalhe/<chapa>')
def detalhe(chapa):
    html=f"<h2>Detalhe {chapa}</h2><a href='/base'>Voltar</a> | <a href='/excel'>Excel</a> | <a href='/graficos'>Gráficos</a><br><br><table border=1 cellpadding=6><tr><th>ITEM</th><th>TAMANHO</th><th>QTD SEPARADA</th><th>FAB</th><th>STATUS</th></tr>"
    try:
        with open(ARQ_INS, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get('chapa','')).zfill(6)==str(chapa).zfill(6):
                    tam=r.get('tamanho','')
                    import re
                    nums=re.findall(r'\d+', tam)
                    qtd=nums[0] if nums else "-"
                    cor="red" if r.get('status')=="Não Conforme" else "green"
                    html+=f"<tr><td>{r.get('item')}</td><td>{tam}</td><td><b>{qtd}</b></td><td>{r.get('data_fab')}</td><td style='color:{cor}'><b>{r.get('status')}</b></td></tr>"
    except: pass
    html+="</table>"
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
            w=csv.DictWriter(f, fieldnames=["data","chapa","nome","cargo","supervisor","coordenador","telefone","eh_motorista","item","tamanho","data_fab","validade","status"])
            w.writeheader(); w.writerows(novas)
        for file in os.listdir(PASTA_MASC):
            if chapa in file:
                try: os.remove(os.path.join(PASTA_MASC,file))
                except: pass
    except: pass
    return f"<script>alert('Chapa {chapa} liberada!');window.location='/base';</script>"

@app_flask.route('/pedidos')
def pedidos():
    html="<h2>Máscaras TXT</h2><a href='/base'>Voltar</a><br><br>"
    try:
        for file in sorted(os.listdir(PASTA_MASC), reverse=True):
            if file.endswith('.txt'):
                with open(os.path.join(PASTA_MASC,file), encoding="utf-8") as txtf: conteudo=txtf.read()
                html+=f"<div style='background:#fffbe6;padding:10px;margin:5px;border:1px solid #ddd'><b>{file}</b> - <a href='/mascaras/{file}' target=_blank>Baixar</a><pre>{conteudo}</pre></div>"
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
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo, caption="🦺 *INSPEÇÃO DE SEGURANÇA - OPERACIONAL*\n\n👇 Digite sua CHAPA:", parse_mode="Markdown")
            return CHAPA
    except: pass
    await update.message.reply_text("🦺 *INSPEÇÃO DE SEGURANÇA - OPERACIONAL*\n\nDigite sua CHAPA:")
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa=update.message.text.strip().zfill(6)
    func=buscar_func(chapa)
    if not func: func=buscar_func(update.message.text.strip())
    if not func:
        await update.message.reply_text(f"❌ Chapa {chapa} não existe.")
        return CHAPA
    if ja_inspecionou(chapa):
        kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")]], resize_keyboard=True)
        await update.message.reply_text(f"⛔ Chapa {chapa} já fez inspeção!", reply_markup=kb)
        return ConversationHandler.END
    context.user_data['chapa']=chapa; context.user_data['func']=func
    cad=buscar_cadastro(chapa)
    if cad and cad.get('telefone'):
        context.user_data['telefone']=cad['telefone']
        kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
        await update.message.reply_text(f"✅ {func['nome']}\nVocê é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return EH_MOTORISTA
    else:
        kb=[[KeyboardButton("📱 Compartilhar telefone", request_contact=True)]]
        await update.message.reply_text(f"✅ {func['nome']}\nCompartilhe telefone:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True))
        return TELEFONE

async def telefone_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tel_raw=update.message.contact.phone_number if update.message.contact else update.message.text
    tel=re.sub(r'\D','',str(tel_raw))[-11:]
    context.user_data['telefone']=tel
    kb=[[KeyboardButton("SIM - Sou motorista"), KeyboardButton("NÃO - Não sou motorista")]]
    await update.message.reply_text(f"Telefone {tel} salvo! Você é motorista?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return EH_MOTORISTA

async def motorista_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.upper()
    eh_mot = "SIM" if "SIM" in texto else "NÃO"
    context.user_data['eh_motorista']=eh_mot
    func=context.user_data['func']
    d={"chapa":context.user_data['chapa'],"nome":func['nome'],"cargo":func['cargo'],"data_admissao":func['admissao'],"supervisor":func['supervisor'],"coordenador":func['coordenador'],"telefone":context.user_data['telefone'],"id_telegram":str(update.effective_user.id),"eh_motorista":eh_mot}
    salvar_cadastro(d)
    if eh_mot=="SIM": context.user_data['itens_filtrados']=ITENS
    else: context.user_data['itens_filtrados']=[i for i in ITENS if i['regra']=="TODOS"]
    context.user_data['item_idx']=0
    return await proximo_item(update, context)

async def proximo_item(update, context):
    idx=context.user_data.get('item_idx',0)
    itens=context.user_data.get('itens_filtrados', ITENS)
    if idx >= len(itens): return await finalizar(update, context)
    item=itens[idx]
    context.user_data['item_atual']=item; context.user_data['tamanho_atual']=""; context.user_data['data_fab_atual']=""; context.user_data['validade_atual']=""
    if item.get('auto_cone'):
        kb=[[KeyboardButton("Utilitário"), KeyboardButton("Passeio")]]
        await update.message.reply_text(f"🚧 {idx+1}/{len(itens)} - {item['nome']}\nSelecione o tipo de veículo:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return CONE_TIPO
    if item.get('auto_mosquetao'):
        kb=[[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("3")]]
        await update.message.reply_text(f"🔗 {idx+1}/{len(itens)} - {item['nome']}\nQuantidade mínima 3!\nSelecione quantidade:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return TAMANHO
    if item.get('tamanho'):
        await update.message.reply_text(f"📏 {idx+1}/{len(itens)} - {item['nome']}\nDigite {item.get('label_tamanho','TAMANHO')}:")
        return TAMANHO
    if item.get('data_fab'):
        await update.message.reply_text(f"📅 {idx+1}/{len(itens)} - {item['nome']}\nDigite DATA FAB DD/MM/AAAA:")
        return DATA_FAB
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"🔍 {idx+1}/{len(itens)} - {item['nome']}\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def cone_tipo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tipo = update.message.text.strip()
    tipo_norm = "Utilitário" if "UTILIT" in tipo.upper() else "Passeio"
    context.user_data['cone_tipo'] = tipo_norm
    if tipo_norm == "Utilitário":
        kb = [[KeyboardButton(str(i)) for i in range(1,6)], [KeyboardButton(str(i)) for i in range(6,11)]]
        await update.message.reply_text(f"🚐 Utilitário - Mínimo 10 cones!\nSelecione quantidade (1 a 10):", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    else:
        kb = [[KeyboardButton(str(i)) for i in range(1,6)]]
        await update.message.reply_text(f"🚗 Passeio - Mínimo 5 cones!\nSelecione quantidade (1 a 5):", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return CONE_QTD

async def cone_qtd_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    qtd = int(texto) if texto.isdigit() else 0
    tipo = context.user_data.get('cone_tipo','Utilitário')
    if tipo == "Utilitário":
        status_auto = "Não Conforme" if qtd < 10 else "Conforme"
    else:
        status_auto = "Não Conforme" if qtd < 5 else "Conforme"
    msg = f"{'🔴' if status_auto=='Não Conforme' else '🟢'} CONES {tipo} QTD {qtd} = {status_auto}!"
    item = context.user_data['item_atual']
    res={"item":f"{item['nome']} - {tipo}","tamanho":f"QTD {qtd} - {tipo}","data_fab":"","validade":"","status":status_auto}
    context.user_data['resultados'].append(res)
    if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
    await update.message.reply_text(msg)
    context.user_data['item_idx']+=1
    return await proximo_item(update, context)

async def tamanho_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item=context.user_data['item_atual']
    texto = update.message.text.strip()
    if item.get('auto_mosquetao'):
        qtd = texto
        status_auto = "Não Conforme" if qtd in ["1","2"] else "Conforme"
        msg = f"🔴 MOSQUETÃO QTD {qtd} = NÃO CONFORME!" if status_auto=="Não Conforme" else f"🟢 MOSQUETÃO QTD {qtd} = CONFORME!"
        res={"item":item['nome'],"tamanho":f"QTD {qtd}","data_fab":"","validade":"","status":status_auto}
        context.user_data['resultados'].append(res)
        if status_auto=="Não Conforme": context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(msg)
        context.user_data['item_idx']+=1
        return await proximo_item(update, context)
    ok, val = validar_tamanho(texto, item.get('tamanho_tipo',''))
    if not ok:
        await update.message.reply_text(f"❌ {val}")
        return TAMANHO
    context.user_data['tamanho_atual']=val
    if item.get('data_fab'):
        await update.message.reply_text(f"Tam {val} OK! Agora DATA FAB:")
        return DATA_FAB
    kb=[[KeyboardButton(o) for o in item['opcoes']]]
    await update.message.reply_text(f"Tam {val} OK! Selecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
    return STATUS

async def data_fab_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto=update.message.text.strip()
    if not re.match(r"\d{2}/\d{2}/\d{4}", texto):
        await update.message.reply_text("❌ Use DD/MM/AAAA")
        return DATA_FAB
    item=context.user_data['item_atual']
    validade, vencido = calcular_validade(texto, item.get('validade_anos',5))
    context.user_data['data_fab_atual']=texto
    context.user_data['validade_atual']=validade
    if vencido:
        res={"item":item['nome'],"tamanho":context.user_data.get('tamanho_atual',''),"data_fab":texto,"validade":validade,"status":"Não Conforme"}
        context.user_data['resultados'].append(res)
        context.user_data['nao_conforme_lista'].append(res)
        await update.message.reply_text(f"⚠️ VENCIDO em {validade}! 🔴 NÃO CONFORME AUTOMÁTICO!")
        context.user_data['item_idx']+=1
        return await proximo_item(update, context)
    else:
        kb=[[KeyboardButton(o) for o in item['opcoes']]]
        await update.message.reply_text(f"📅 Validade {validade} - OK ✅\nSelecione:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return STATUS

async def status_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status=update.message.text.strip()
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
    msg=f"✅ FINALIZADA!\n\nCHAPA: {chapa}\nNÃO CONF: {len(nao_conf)}\n\n📋 MÁSCARA:\n{txt_conteudo}"
    await update.message.reply_text(msg)
    if os.path.exists(caminho_txt):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(caminho_txt, "rb"), filename=os.path.basename(caminho_txt), caption="📄 MÁSCARA TXT")
    kb = ReplyKeyboardMarkup([[KeyboardButton("🔄 NOVA INSPEÇÃO - /start")],[KeyboardButton("/start")]], resize_keyboard=True)
    await update.message.reply_text("👇 Para NOVA solicitação clique:", reply_markup=kb)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("/start - Nova Inspeção")]], resize_keyboard=True)
    await update.message.reply_text("Cancelado! /start para recomeçar", reply_markup=kb)
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
            CONE_TIPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_tipo_step)],
            CONE_QTD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cone_qtd_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
