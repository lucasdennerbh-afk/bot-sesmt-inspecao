import os
import logging
from io import BytesIO
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ========= 35 PERGUNTAS =========
PERGUNTAS_LISTA = [
"1-Uniforme", "2-EPI adequado", "3-EPI em bom estado", "4-Capacete", "5-Capacete com jugular",
"6-Óculos de segurança", "7-Luva", "8-Bota", "9-Cinto de segurança", "10-Talabarte",
"11-Organização do local", "12-Sinalização", "13-Ferramentas", "14-Ferramentas em bom estado",
"15-Escada", "16-Andaime", "17-Trabalho em altura", "18-PT liberada", "19-Análise de risco",
"20-Conhecimento da atividade", "21-Comunicação", "22-Hidratação", "23-Descanso",
"24-Alimentação", "25-Transporte", "26-Celular", "27-Fumo", "28-Álcool/Drogas",
"29-Postura", "30-Movimentação manual", "31-Ruído", "32-Iluminação", "33-Ventilação",
"34-Limpeza", "35-Descarte de resíduos"
]

# ESTADOS CONVERSA
CHAPA, NOME, CARGO, SUPERVISOR, COORDENADOR, PERGUNTAS = range(6)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ========= FILTRO BASE =========
def montar_filtro_base(args_text):
    where = []
    params = []
    if not args_text:
        return "", []
    txt_lower = args_text.lower()
    txt_upper = args_text.upper()

    if "chapa" in txt_lower:
        try:
            chapa = txt_lower.split("chapa")[1].strip().split()[0]
            where.append("chapa = %s")
            params.append(chapa)
        except: pass

    if "supervisor" in txt_lower:
        try:
            # pega tudo depois de supervisor até coordenador/chapa/data
            parte = txt_lower.split("supervisor")[1]
            for sep in ["coordenador", "chapa", "data", "hoje", "ontem", "semana"]:
                if sep in parte:
                    parte = parte.split(sep)[0]
            sup = parte.strip().upper()
            if sup:
                where.append("supervisor ILIKE %s")
                params.append(f"%{sup}%")
        except: pass

    if "coordenador" in txt_lower:
        try:
            parte = txt_lower.split("coordenador")[1]
            for sep in ["supervisor", "chapa", "data", "hoje", "ontem", "semana"]:
                if sep in parte:
                    parte = parte.split(sep)[0]
            coord = parte.strip().upper()
            if coord:
                where.append("coordenador ILIKE %s")
                params.append(f"%{coord}%")
        except: pass

    if "HOJE" in txt_upper:
        where.append("DATE(data) = CURRENT_DATE")
    elif "ONTEM" in txt_upper:
        where.append("DATE(data) = CURRENT_DATE - 1")
    elif "SEMANA" in txt_upper:
        where.append("data >= CURRENT_DATE - INTERVAL '7 days'")

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    return where_sql, params

# ========= START INSPECAO =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['respostas'] = {}
    await update.message.reply_text("🔧 *TELE MONT - Inspeção*\n\nDigite a CHAPA:", parse_mode='Markdown')
    return CHAPA

async def chapa_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['chapa'] = update.message.text.strip()
    await update.message.reply_text("Nome do colaborador:")
    return NOME

async def nome_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nome'] = update.message.text.strip().upper()
    await update.message.reply_text("Cargo:")
    return CARGO

async def cargo_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cargo'] = update.message.text.strip().upper()
    await update.message.reply_text("Supervisor:")
    return SUPERVISOR

async def supervisor_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['supervisor'] = update.message.text.strip().upper()
    await update.message.reply_text("Coordenador:")
    return COORDENADOR

async def coordenador_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['coordenador'] = update.message.text.strip().upper()
    context.user_data['pergunta_idx'] = 0
    await update.message.reply_text(f"Vamos começar (35 perguntas):\n\n*1 - {PERGUNTAS_LISTA[0]}*\nResponda: OK / NÃO OK / N/A", parse_mode='Markdown')
    return PERGUNTAS

async def perguntas_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['pergunta_idx']
    resposta = update.message.text.strip().upper().replace("NAO OK","NÃO OK")
    if resposta not in ["OK","NÃO OK","N/A","NA"]:
        await update.message.reply_text("Responda apenas: OK / NÃO OK / N/A")
        return PERGUNTAS

    if resposta == "NA": resposta = "N/A"
    context.user_data['respostas'][f'p{idx+1}'] = resposta
    idx += 1
    context.user_data['pergunta_idx'] = idx

    if idx < 35:
        await update.message.reply_text(f"*{idx+1} - {PERGUNTAS_LISTA[idx]}*\nOK / NÃO OK / N/A", parse_mode='Markdown')
        return PERGUNTAS
    else:
        # SALVAR - CORRIGIDO SEM DUPLICAR
        try:
            conn = get_conn()
            cur = conn.cursor()
            cols = ", ".join([f"p{i}" for i in range(1,36)])
            vals = ", ".join(["%s"]*35)
            resp_list = [context.user_data['respostas'][f'p{i}'] for i in range(1,36)]
            
            sql = f"INSERT INTO inspecoes (chapa, nome, cargo, supervisor, coordenador, data, {cols}) VALUES (%s,%s,%s,%s,%s,NOW(),{vals})"
            cur.execute(sql, [context.user_data['chapa'], context.user_data['nome'], context.user_data['cargo'], context.user_data['supervisor'], context.user_data['coordenador']] + resp_list)
            conn.commit()
            cur.close()
            conn.close()
            await update.message.reply_text("✅ Inspeção salva com sucesso! Use /base /graficos /naoconforme")
        except Exception as e:
            logger.error(e)
            await update.message.reply_text(f"Erro ao salvar: {e}")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END

# ========= BASE COM FILTROS =========
async def base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args_text = " ".join(context.args) if context.args else ""
        where_sql, params = montar_filtro_base(args_text)
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT COUNT(*) as total, COUNT(DISTINCT chapa) as pessoas FROM inspecoes {where_sql}", params)
        info = cur.fetchone()
        if info['total'] == 0:
            await update.message.reply_text(f"📊 Nenhum dado com filtro: {args_text}\nEx: /base supervisor LUCAS")
            cur.close(); conn.close(); return
        cur.execute(f"SELECT chapa, nome, supervisor, COUNT(*) as qtd FROM inspecoes {where_sql} GROUP BY chapa, nome, supervisor ORDER BY qtd DESC LIMIT 10", params)
        top = cur.fetchall()
        cur.close(); conn.close()
        msg = f"📊 *BASE - TELE MONT*\nFiltro: `{args_text if args_text else 'GERAL'}`\nTotal: *{info['total']}* | Pessoas: *{info['pessoas']}*\n\n*Top:*\n"
        for t in top:
            msg += f"{t['chapa']} - {t['nome'][:15]} ({t['supervisor'][:10]}): {t['qtd']}\n"
        msg += "\nFiltros: /base supervisor NOME /base coordenador NOME /base hoje"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro base: {e}")

# ========= GRAFICOS COM FILTROS =========
async def graficos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Gerando gráficos...")
    try:
        args_text = " ".join(context.args) if context.args else ""
        where_sql, params = montar_filtro_base(args_text)
        conn = get_conn()
        df = pd.read_sql(f"SELECT * FROM inspecoes {where_sql}", conn, params=params)
        conn.close()
        if df.empty:
            await update.message.reply_text("Sem dados com esse filtro"); return
        cols = [f'p{i}' for i in range(1,36)]
        todos = []
        for c in cols:
            if c in df.columns:
                todos.extend(df[c].dropna().astype(str).tolist())
        todos = [v.upper().replace("NAO OK","NÃO OK") for v in todos]
        ok = todos.count('OK'); nok = todos.count('NÃO OK'); na = todos.count('N/A')
        plt.figure(figsize=(7,5))
        plt.pie([ok, nok, na], labels=[f'OK {ok}', f'NÃO OK {nok}', f'N/A {na}'], autopct='%1.1f%%', colors=['#2ecc71','#e74c3c','#95a5a6'])
        plt.title(f'CONFORMIDADE - {args_text.upper() if args_text else "GERAL"} - {len(df)} insp.')
        buf = BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); plt.close()
        await update.message.reply_photo(photo=buf, caption=f"OK={ok} | NOK={nok} | {ok/(ok+nok)*100 if ok+nok else 0:.1f}% OK - Filtro: {args_text if args_text else 'GERAL'}")
    except Exception as e:
        await update.message.reply_text(f"Erro graficos: {e}")

# ========= NAO CONFORME COM % =========
async def naoconforme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args_text = " ".join(context.args) if context.args else ""
        where_sql, params = montar_filtro_base(args_text)
        conn = get_conn()
        df = pd.read_sql(f"SELECT * FROM inspecoes {where_sql}", conn, params=params)
        conn.close()
        if df.empty:
            await update.message.reply_text(f"📊 Nenhuma inspeção com filtro: {args_text}\nEx: /naoconforme supervisor LUCAS"); return

        cols = [f'p{i}' for i in range(1,36)]
        lista = []
        for i, col in enumerate(cols):
            if col in df.columns:
                qtd = (df[col].astype(str).str.upper().str.contains('NÃO OK|NAO OK')).sum()
                lista.append({"ITEM": PERGUNTAS_LISTA[i], "QTD_NAO_OK": int(qtd)})
        
        df_lista = pd.DataFrame(lista)
        df_lista = df_lista[df_lista['QTD_NAO_OK'] > 0].sort_values('QTD_NAO_OK', ascending=False)
        total_nc = int(df_lista['QTD_NAO_OK'].sum()) if not df_lista.empty else 0
        if df_lista.empty:
            await update.message.reply_text(f"✅ Nenhum NÃO CONFORME - Tudo OK! Filtro: {args_text if args_text else 'GERAL'}"); return

        df_lista['%_DO_TOTAL_NC'] = (df_lista['QTD_NAO_OK'] / total_nc * 100).round(1)
        df_lista['%_REPROVACAO'] = (df_lista['QTD_NAO_OK'] / len(df) * 100).round(1)

        msg = f"🚨 *NÃO CONFORMES - SOMATÓRIO*\nFiltro: `{args_text if args_text else 'GERAL'}`\nInsp: *{len(df)}* | Total NC: *{total_nc}*\n\n"
        for _, row in df_lista.iterrows():
            msg += f"{row['ITEM']}: *{row['QTD_NAO_OK']}x* ({row['%_DO_TOTAL_NC']}% do NC | {row['%_REPROVACAO']}% reprova)\n"
        if len(msg) > 3500: msg = msg[:3500] + "\n... completo no Excel"
        await update.message.reply_text(msg, parse_mode='Markdown')

        plt.figure(figsize=(11, max(5, len(df_lista)*0.5)))
        plt.barh(df_lista['ITEM'][::-1].str[:35], df_lista['QTD_NAO_OK'][::-1], color='#e74c3c')
        for i, (qtd, perc) in enumerate(zip(df_lista['QTD_NAO_OK'][::-1], df_lista['%_DO_TOTAL_NC'][::-1])):
            plt.text(qtd + 0.2, i, f"{qtd}x ({perc}%)", va='center', fontsize=9, fontweight='bold')
        plt.title(f'NÃO CONFORMES - {args_text.upper() if args_text else "GERAL"} - {len(df)} insp | {total_nc} NC', fontweight='bold')
        plt.tight_layout()
        buf = BytesIO(); plt.savefig(buf, format='png', dpi=150, bbox_inches='tight'); buf.seek(0); plt.close()
        await update.message.reply_photo(photo=buf, caption=f"Filtro: {args_text if args_text else 'GERAL'} | Total NC: {total_nc}")

        buf_excel = BytesIO()
        df_lista.to_excel(buf_excel, index=False)
        buf_excel.seek(0)
        nome_arq = f"NC_{args_text.replace(' ','_') if args_text else 'GERAL'}_{datetime.now().strftime('%d-%m')}.xlsx"
        await update.message.reply_document(document=buf_excel, filename=nome_arq, caption=f"📥 Excel: {args_text if args_text else 'GERAL'}")

    except Exception as e:
        logger.error(e); await update.message.reply_text(f"Erro: {e}")

async def excel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args_text = " ".join(context.args) if context.args else ""
        where_sql, params = montar_filtro_base(args_text)
        conn = get_conn()
        df = pd.read_sql(f"SELECT * FROM inspecoes {where_sql} ORDER BY data DESC", conn, params=params)
        conn.close()
        buf = BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
        await update.message.reply_document(document=buf, filename=f"BASE_{args_text if args_text else 'GERAL'}.xlsx")
    except Exception as e:
        await update.message.reply_text(f"Erro excel: {e}")

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chapa_step)],
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, nome_step)],
            CARGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, cargo_step)],
            SUPERVISOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, supervisor_step)],
            COORDENADOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, coordenador_step)],
            PERGUNTAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, perguntas_step)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("base", base))
    app.add_handler(CommandHandler("graficos", graficos))
    app.add_handler(CommandHandler("naoconforme", naoconforme))
    app.add_handler(CommandHandler("excel", excel_cmd))
    print("Bot rodando... Supabase OK!")
    app.run_polling()

if __name__ == "__main__":
    main()
