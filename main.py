import logging
from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes

from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import InlineQueryHandler

from uuid import uuid4

import os # for accessing environment variables
from dotenv import load_dotenv # for loading environment variables from .env file

# imports for google sheet api
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

# import for nice printing
from pprint import pp

# import for data manipulation
import pandas as pd
import numpy as np

# for date calculations
from datetime import date
import datetime

load_dotenv()  # Load environment variables from .env file



logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

async def caps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_caps = ' '.join(context.args).upper()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_caps)

async def inline_caps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return
    results = []
    results.append(
        InlineQueryResultArticle(
            id=str(uuid4()),
            title='Caps',
            input_message_content=InputTextMessageContent(query.upper())
        )
    )
    await context.bot.answer_inline_query(update.inline_query.id, results)

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")

async def generate_team_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    range_name = "League 1 Games!4:7" # adjust range as needed
    # authenticate google sheets api using service account credentials from .env
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CREDENTIALS")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json), 
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    # obtain data from spreadsheet using google sheets api
    try:
        service = build("sheets", "v4", credentials=creds)

        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        rows = result.get("values", [])
        print(f"{len(rows)} rows retrieved")
    except HttpError as error:
        print(f"An error occurred: {error}")
        return error


    try:
        pp(rows, width=100, compact=True) # pretty print the rows for debugging
    except Exception as e:
        print(f"Error pretty printing rows: {e}")
        return e

    pp(rows, width=100, compact=True) # pretty print the rows for debugging
    
    # change data into a df for easier manipulation
    df_rows = pd.DataFrame(rows)
    df_rows = df_rows.transpose() # transpose the df so that headers are first row

    # Find the row index where the first non-empty value is 'Date'
    header_idx = df_rows[df_rows[0].str.strip() == 'Date'].index[0]
    
    df_rows.columns = df_rows.loc[header_idx] # set that specific row as header
    df_rows = df_rows.loc[header_idx + 1:] # keep everything after the header row

    # remove data point with "Attendance Percentage"
    df_rows = df_rows.replace("Attendance Percentage", np.nan) 
    df_rows = df_rows.dropna()

    df_rows.info() # print info about the df for debugging 
    print(df_rows) # print first 5 rows of the df for debugging

    # obtain game date nearest to today, and haven't passed yet
    today = np.datetime64('today')
    print(today)
    df_rows['Date'] = pd.to_datetime(df_rows['Date'], errors='raise', format='%d %B %Y %A')
    df_rows.info()
    nearest_idx = df_rows[df_rows['Date'] >= today].index[0]
    nearest_row = df_rows.loc[nearest_idx]
    print(nearest_row) # print nearest row for debugging

    # obtain template message for nearest team game
    next_game_date = nearest_row['Date'].strftime('%d %B %Y %A') # convert date back to string for sending to telegram bot
    next_game_time = nearest_row['Time']
    next_game_opponent = nearest_row['Games']
    next_game_location = nearest_row['Location']
    next_game_reporting_time = datetime.datetime.strptime(nearest_row['Time'], "%H:%M:%S") - datetime.timedelta(minutes=45)
    next_game_reporting_time = next_game_reporting_time.strftime("%H:%M:%S") 
    
    team_message = f"""
{next_game_date} vs {next_game_opponent} @ {next_game_location} 
Game time: {next_game_time}
Reporting time: {next_game_reporting_time}

Bring both blue and white top & black and white socks

Don't be late if not fine!!
    """ 
    
    # df_rows['Date'] = df_rows['Date'].dt.strftime('%d %B %Y %A') # convert date back to string for sending to telegram bot
    # df_string = df_rows.to_string() # convert df to string for sending to telegram bot
    
    # send message to user by telegram bot
    # team_message = f"Upcoming Games: \n {df_string} \n\n"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=team_message)


if __name__ == '__main__':
    application = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    start_handler = CommandHandler('start', start)
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)

    caps_handler = CommandHandler('caps', caps)

    inline_caps_handler = InlineQueryHandler(inline_caps)

    team_handler = CommandHandler('team', generate_team_message)

    unknown_handler = MessageHandler(filters.COMMAND, unknown)

    application.add_handler(inline_caps_handler)
    application.add_handler(start_handler)
    application.add_handler(echo_handler)
    application.add_handler(caps_handler)
    application.add_handler(team_handler)
    application.add_handler(unknown_handler)
    
    application.run_polling()