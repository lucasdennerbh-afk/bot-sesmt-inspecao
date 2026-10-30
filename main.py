import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ========= CONFIG =========
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHAPAS = ["062289", "065432"] # coloque sua chapa aqui

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ESTADOS
CHAPA, PERGUNTAS, CAD_CHAPA, CAD_NOME, CAD_CARGO, CAD_SUP, CAD_COORD = range(7)

PERGUNTAS_LISTA = [
    "1 - Uniforme limpo e completo?", "2 - EPI adequado à atividade?", "3 - Cinto de segurança?", "4 - Calçado de segurança?",
    "5 - Luvas em bom estado?", "6 - Capacete com jugular?", "7 - Óculos de proteção?", "8 - Protetor auricular?",
    "9 - Máscara / Respirador?", "10 - Ferramentas em bom estado?", "11 - Organização do local?", "12 - Sinalização de segurança?",
    "13 - Extintor de incêndio próximo?", "14 - Kit primeiros socorros?", "15 - Iluminação adequada?", "16 - Ventilação?",
    "17 - Ruído controlado?", "18 - Postura ergonômica?", "19 - Hidratação disponível?", "20 - Pausas previstas?",
    "21 - Treinamento em dia?", "22 - ASO válido?", "23 - Integração realizada?", "24 - DDS realizado hoje?",
    "25 - PT emitida?", "26 - APR preenchida?", "27 - Bloqueio e etiquetagem?", "28 - Trabalho em altura liberado?",
    "29 - Espaço confinado liberado?", "30 - Risco elétrico controlado?", "31 - Produtos químicos identificados?",
    "32 - Proteção de máquinas?", "33 - Veículos e equipamentos inspecionados?", "34 - Casa de força organizada?",
    "35 - Observações finais / Comportamento seguro?"
]

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cadastros (
                chapa TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                cargo TEXT,
                supervisor TEXT,
                coordenador TEXT,
                data_cadastro TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inspecoes (
                id SERIAL PRIMARY KEY,
                data TIMESTAMP DEFAULT NOW(),
                chapa TEXT,
                nome TEXT,
                cargo TEXT,
                supervisor TEXT,
                coordenador TEXT,
                p1 TEXT, p2 TEXT, p3 TEXT, p4 TEXT, p5 TEXT, p6 TEXT, p7 TEXT, p8 TEXT, p9 TEXT, p10 TEXT,
                p11 TEXT, p12 TEXT, p13 TEXT, p14 TEXT, p15 TEXT, p16 TEXT, p17 TEXT, p18 TEXT, p19 TEXT, p20 TEXT,
                p21 TEXT, p22 TEXT, p23 TEXT, p24 TEXT, p25 TEXT, p26 TEXT, p27 TEXT, p28 TEXT, p29 TEXT, p30 TEXT,
                p31 TEXT, p32 TEXT, p33 TEXT, p34 TEXT, p35 TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS justificativas (
                id SERIAL PRIMARY KEY,
                data TIMESTAMP DEFAULT NOW(),
                chapa TEXT,
                nome TEXT,
                justificativa TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pedidos_mascaras (
                id SERIAL PRIMARY KEY,
                data TIMESTAMP DEFAULT NOW(),
                chapa TEXT,
                nome TEXT,
                qtd INTEGER
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("Supabase OK!")
        logger.info("Supabase OK!")
    except Exception as e:
        print(f"Erro Supabase init: {e}")
        logger.error(f"Erro Supabase init: {e}")

# ========= START E INSPECAO =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🔍 *Bot SESMT Telemont*\n\nDigite sua chapa:", parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
    return CHAPA

async def receber_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa = update.message.text.strip()
    context.user_data['chapa'] = chapa
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM cadastros WHERE chapa = %s", (chapa,))
        cad = cur.fetchone()
        cur.close()
        conn.close()
        if not cad:
            await update.message.reply_text(f"❌ Chapa {chapa} não cadastrada.\n\nFale com o SESMT ou use /cadastrar (admin).")
            return ConversationHandler.END
        
        context.user_data['cadastro'] = cad
        context.user_data['respostas'] = []
        context.user_data['inicio'] = datetime.now()
        
        await update.message.reply_text(
            f"👷 *{cad['nome']}*\nCargo: {cad['cargo']}\n\nVamos começar a inspeção.\n\n*1/35* - {PERGUNTAS_LISTA[0]}",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["OK", "NÃO OK", "N/A"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return PERGUNTAS
    except Exception as e:
        logger.error(e)
        await update.message.reply_text(f"Erro ao buscar chapa: {e}")
        return ConversationHandler.END

async def receber_perguntas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().upper()
    if texto not in ["OK", "NÃO OK", "NAO OK", "N/A", "NA"]:
        texto = update.message.text.strip()
        if "NAO" in texto.upper():
            texto = "NÃO OK"
    
    if texto == "NAO OK":
        texto = "NÃO OK"
    if texto == "NA":
        texto = "N/A"
        
    context.user_data['respostas'].append(texto)
    idx = len(context.user_data['respostas'])
    
    if idx < 35:
        await update.message.reply_text(
            f"*{idx+1}/35* - {PERGUNTAS_LISTA[idx]}",
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["OK", "NÃO OK", "N/A"]], one_time_keyboard=True, resize_keyboard=True)
        )
        return PERGUNTAS
    else:
        # SALVA 1 LINHA SÓ - CORREÇÃO PRINCIPAL
        try:
            cad = context.user_data['cadastro']
            respostas = context.user_data['respostas']
            chapa = context.user_data['chapa']
            
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO inspecoes (chapa, nome, cargo, supervisor, coordenador,
                p1,p2,p3,p4,p5,p6,p7,p8,p9,p10,p11,p12,p13,p14,p15,p16,p17,p18,p19,p20,p21,p22,p23,p24,p25,p26,p27,p28,p29,p30,p31,p32,p33,p34,p35)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (chapa, cad['nome'], cad['cargo'], cad['supervisor'], cad['coordenador'], *respostas))
            conn.commit()
            cur.close()
            conn.close()
            
            tempo = (datetime.now() - context.user_data['inicio']).seconds
            await update.message.reply_text(
                f"✅ *Inspeção salva com sucesso!*\n\n👷 {cad['nome']}\n⏱️ Tempo: {tempo}s\n💾 1 linha salva no Supabase (não apaga mais no restart)\n\nUse:\n/base - ver total\n/graficos - ver análise\n/excel - baixar planilha",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            logger.error(f"Erro ao salvar: {e}")
            await update.message.reply_text(f"❌ Erro ao salvar: {e}", reply_markup=ReplyKeyboardRemove())
        
        return ConversationHandler.END

# ========= COMANDOS BASE, GRAFICOS, EXCEL =========
async def base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as total, COUNT(DISTINCT chapa) as pessoas FROM inspecoes")
        info = cur.fetchone()
        cur.execute("SELECT chapa, nome, cargo, COUNT(*) as qtd, MAX(data) as ultima FROM inspecoes GROUP BY chapa, nome, cargo ORDER BY qtd DESC LIMIT 15")
        top = cur.fetchall()
        cur.close()
        conn.close()
        
        if info['total'] == 0:
            await update.message.reply_text("📊 Base vazia. Faça uma inspeção com /start")
            return

        msg = f"📊 *BASE SUPABASE - TELE MONT*\n\nTotal inspeções: *{info['total']}*\nPessoas diferentes: *{info['pessoas']}*\n\n*Top Inspetores:*\n"
        for t in top:
            msg += f"{t['chapa']} - {t['nome'][:20]}: {t['qtd']}\n"
        msg += "\nComandos:\n/graficos - Análise detalhada\n/excel - Baixar Excel"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Erro base: {e}")

async def graficos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Gerando gráficos... aguarde")
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM inspecoes ORDER BY data DESC", conn)
        conn.close()
        
        if df.empty:
            await update.message.reply_text("Nenhuma inspeção ainda. Use /start")
            return

        cols = [f'p{i}' for i in range(1,36)]
        todos_valores = []
        for c in cols:
            if c in df.columns:
                todos_valores.extend(df[c].dropna().astype(str).tolist())
        
        # Normaliza
        todos_valores = [v.upper().strip() for v in todos_valores]
        todos_valores = ["NÃO OK" if "NAO" in v else v for v in todos_valores]
        todos_valores = ["N/A" if v == "NA" else v for v in todos_valores]
        
        ok = todos_valores.count('OK')
        nok = todos_valores.count('NÃO OK')
        na = todos_valores.count('N/A')
        total_itens = len(todos_valores)

        # GRAFICO 1 - PIZZA GERAL
        plt.figure(figsize=(7,5))
        cores = ['#2ecc71', '#e74c3c', '#95a5a6']
        plt.pie([ok, nok, na], labels=[f'OK ({ok})', f'NÃO OK ({nok})', f'N/A ({na})'], autopct='%1.1f%%', colors=cores, startangle=90)
        plt.title(f'ANÁLISE GERAL - TELE MONT\n{len(df)} inspeções | {total_itens} itens avaliados', fontsize=11, fontweight='bold')
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        await update.message.reply_photo(photo=buf, caption=f"📊 GERAL: OK={ok} | NÃO OK={nok} | N/A={na} | Taxa conformidade: {ok/total_itens*100:.1f}%")

        # GRAFICO 2 - TOP 10 PIORES ITENS
        problemas = {}
        for i, col in enumerate(cols):
            if col in df.columns:
                count_nok = (df[col].astype(str).str.upper().str.contains('NÃO OK|NAO OK')).sum()
                problemas[PERGUNTAS_LISTA[i]] = count_nok
        
        piores = sorted(problemas.items(), key=lambda x: x[1], reverse=True)[:10]
        if piores and piores[0][1] > 0:
            nomes, valores = zip(*piores)
            plt.figure(figsize=(10,6))
            plt.barh(nomes[::-1], valores[::-1], color='#e74c3c')
            plt.xlabel('Qtd de NÃO OK')
            plt.title('TOP 10 ITENS COM MAIS NÃO OK - PONTOS CRÍTICOS', fontweight='bold')
            plt.tight_layout()
            buf2 = BytesIO()
            plt.savefig(buf2, format='png', dpi=150, bbox_inches='tight')
            buf2.seek(0)
            plt.close()
            await update.message.reply_photo(photo=buf2, caption="🚨 Itens críticos que precisam de ação")

        # GRAFICO 3 - EVOLUÇÃO POR DIA
        if len(df) > 1:
            df['data_dia'] = pd.to_datetime(df['data']).dt.date
            evol = df.groupby('data_dia').size()
            plt.figure(figsize=(8,4))
            plt.plot(evol.index.astype(str), evol.values, marker='o', color='#3498db', linewidth=2)
            plt.xticks(rotation=45)
            plt.ylabel('Inspeções')
            plt.title('Evolução de Inspeções por Dia')
            plt.tight_layout()
            buf3 = BytesIO()
            plt.savefig(buf3, format='png', dpi=150, bbox_inches='tight')
            buf3.seek(0)
            plt.close()
            await update.message.reply_photo(photo=buf3, caption="📈 Evolução diária")

        await update.message.reply_text("✅ Gráficos finalizados! Use /excel para baixar planilha completa.")

    except Exception as e:
        logger.error(f"Erro graficos: {e}")
        await update.message.reply_text(f"❌ Erro nos gráficos: {e}\n\nSe ainda tiver linhas duplicadas antigas (35 linhas por inspeção), apague tudo no Supabase > inspecoes > Delete all e faça 1 inspeção nova teste.")

async def excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        df = pd.read_sql("SELECT * FROM inspecoes ORDER BY data DESC", conn)
        conn.close()
        if df.empty:
            await update.message.reply_text("Base vazia.")
            return
        buf = BytesIO()
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        await update.message.reply_document(document=buf, filename=f"TELEMONT_inspecoes_{datetime.now().strftime('%d-%m-%Y')}.xlsx", caption=f"📊 {len(df)} inspeções exportadas")
    except Exception as e:
        await update.message.reply_text(f"Erro excel: {e}")

async def cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chapa_user = str(update.effective_user.id)
    # Simplificado: libera para todos por enquanto
    await update.message.reply_text("📝 Cadastro de chapa - Digite a chapa:")
    return CAD_CHAPA

async def cad_chapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['nova_chapa'] = update.message.text.strip()
    await update.message.reply_text("Nome completo:")
    return CAD_NOME

async def cad_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['novo_nome'] = update.message.text.strip()
    await update.message.reply_text("Cargo:")
    return CAD_CARGO

async def cad_cargo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['novo_cargo'] = update.message.text.strip()
    await update.message.reply_text("Supervisor:")
    return CAD_SUP

async def cad_sup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['novo_sup'] = update.message.text.strip()
    await update.message.reply_text("Coordenador:")
    return CAD_COORD

async def cad_coord(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cadastros (chapa, nome, cargo, supervisor, coordenador)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (chapa) DO UPDATE SET nome=%s, cargo=%s, supervisor=%s, coordenador=%s
        """, (
            context.user_data['nova_chapa'], context.user_data['novo_nome'], context.user_data['novo_cargo'],
            context.user_data['novo_sup'], update.message.text.strip(),
            context.user_data['novo_nome'], context.user_data['novo_cargo'], context.user_data['novo_sup'], update.message.text.strip()
        ))
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Chapa {context.user_data['nova_chapa']} cadastrada!")
    except Exception as e:
        await update.message.reply_text(f"Erro cadastro: {e}")
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv_inspecao = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_chapa)],
            PERGUNTAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_perguntas)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    
    conv_cad = ConversationHandler(
        entry_points=[CommandHandler("cadastrar", cadastrar)],
        states={
            CAD_CHAPA: [MessageHandler(filters.TEXT & ~filters.COMMAND, cad_chapa)],
            CAD_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cad_nome)],
            CAD_CARGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, cad_cargo)],
            CAD_SUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, cad_sup)],
            CAD_COORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, cad_coord)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    
    app.add_handler(conv_inspecao)
    app.add_handler(conv_cad)
    app.add_handler(CommandHandler("base", base))
    app.add_handler(CommandHandler("graficos", graficos))
    app.add_handler(CommandHandler("excel", excel))
    app.add_handler(CommandHandler("cancelar", cancelar))
    
    print("Bot Telemont rodando com Supabase...")
    app.run_polling()

if __name__ == "__main__":
    main()
