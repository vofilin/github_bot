#!/usr/bin/env python

"""
Bot for triggering worflow in a github repository.

Usage: Example of a bot-user conversation using ConversationHandler.
The bot uses following environmental variables:
URL - url of the project API, like
https://api.github.com/repos/vofilin/cocktail_master_infra
BOT_TOKEN - Token for your bot, which you can get from the bot_father
AUTH_TOKEN - Access token for github with "repo" rights
RESTRICTED_IDS - Comma separated Telegram user IDs who can trigger the bot.
Send /workflow to initiate the conversation.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
import requests
import os

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (Updater, CommandHandler, MessageHandler,
    ConversationHandler, CallbackContext, Filters)
from requests.exceptions import HTTPError
from functools import wraps

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

URL = os.environ.get('URL')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
AUTH_TOKEN = "token " + os.environ.get('AUTH_TOKEN')
RESTRICTED_IDS = os.environ.get('RESTRICTED_IDS').split(",")
RESTRICTED_IDS = list(map(int, RESTRICTED_IDS))
MODE, TAG, WORKFLOW = range(3)

# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def help(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Send /workflow to start working with the bot.\n'
        'Follow the bots instructions:\n'
        '1. Choose the target branch for workflow\n'
        '2. Choose the workflow mode (create or delete infrastructure)\n'
        '3. Choose version of the app by replying to the bot '
        '(either version or "latest" can be used).')


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning(f'Update {update} caused error {context.error}.')


def restricted(func):
    """Restrict usage of func to allowed users only and replies if necessary"""
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user = update.effective_user
        if user.id not in RESTRICTED_IDS:
            logger.error(f'Unauthorized access denied for {user}. '
            f'RESTRICTED_IDS: {RESTRICTED_IDS}')
            update.message.reply_text('Access to this command is restricted.')
            return  # quit function
        return func(update, context, *args, **kwargs)
    return wrapped


@restricted
def branch(update, context):
    """Choose branch"""
    url = URL+'/branches'
    reply_keyboard = []
    replies = []
    user = update.message.from_user
    try:
        response = requests.get(
            url,
            headers = {'Accept': 'application/vnd.github.v3+json',
                       'Authorization': AUTH_TOKEN})
        response.raise_for_status()
    except HTTPError as http_err:
        logger.error (f'HTTP error occurred: {http_err} '
                      f'{response.request.url} '
                      f'{response.request.headers}'
                      f'{response.request.body}'
                      f'{response.text}')
        update.message.reply_text (f'HTTP error occurred: {http_err}')
        update.message.reply_text (f'Response: {response.text}')
    except Exception as err:
        logger.error (f'Other error occurred: {err}')
        update.message.reply_text (f'Other error occurred: {err}')
    else:
        logger.info(f'User {user.last_name} {user.first_name} started the conversation.')
        for branch in response.json():
            replies.append(branch["name"])
        reply_keyboard.append(replies)
        update.message.reply_text(f'Choose branch\n'
             f'Send /cancel to stop talking to me.',
             reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
        return MODE


@restricted
def mode(update, context):
    """Choose workflow mode"""
    reply_keyboard = [['create', 'destroy']]
    context.user_data["branch"] = update.message.text
    update.message.reply_text (f'Chosen branch: {context.user_data["branch"]}\n'
        f'Choose workflow mode (create or destroy)\n'
        f'Send /cancel to stop talking to me.',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return TAG


@restricted
def tag(update, context):
    """Choose application tag"""
    context.user_data["mode"] = update.message.text
    update.message.reply_text (f'Chosen branch: {context.user_data["branch"]}\n'
        f'Chosen workflow mode: {context.user_data["mode"]}\n'
        f'Choose application version. Reply "latest" for latest version\n'
        f'Send /cancel to stop talking to me.',
        reply_markup=ReplyKeyboardRemove())
    return WORKFLOW


@restricted
def workflow(update, context):
    """Run worflow"""
    context.user_data["tag"] = update.message.text
    url = URL+'/actions/workflows/ci.yaml/dispatches'

    update.message.reply_text (
        f'{"Creating" if context.user_data["mode"] == "create" else "Destroying"} '
        f'infrastructure for Cocktail Master v "{context.user_data["tag"]}" '
        f'in branch "{context.user_data["branch"]}"')

    logger.info(
        f'Starting workflow. '
        f'Mode: {context.user_data["mode"]}. '
        f'Branch: {context.user_data["branch"]}. '
        f'Tag: {context.user_data["tag"]}.')
    try:
        response = requests.post(
            url,
            headers = {'Accept': 'application/vnd.github.v3+json',
                       'Authorization': AUTH_TOKEN},
            json = {'ref':context.user_data["branch"],
                    'inputs':{'mode':context.user_data["mode"],
                    'image_tag':context.user_data["tag"]}})
        response.raise_for_status()
    except HTTPError as http_err:
        logger.error (f'HTTP error occurred: {http_err} '
                      f'{response.request.url} '
                      f'{response.request.headers}'
                      f'{response.request.body}'
                      f'{response.text}')
        update.message.reply_text (f'HTTP error occurred: {http_err}')
        update.message.reply_text (f'Response: {response.text}')
    except Exception as err:
        logger.error (f'Other error occurred: {err}.')
        update.message.reply_text (f'Other error occurred: {err}.')
    else:
        logger.info(f'Workflow started.')
        return ConversationHandler.END


def cancel(update, context):
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info(f'User {user.last_name} {user.first_name} canceled the conversation.')
    update.message.reply_text(
        'Workflow canceled.',
        reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(BOT_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    # dp.add_handler(CommandHandler("workflow", workflow))
    dp.add_handler(CommandHandler('help', help))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('workflow', branch)],
        states={
            MODE: [MessageHandler(Filters.text & ~Filters.command, mode)],
            TAG: [MessageHandler(Filters.regex('^(create|destroy)$'), tag)],
            WORKFLOW: [MessageHandler(Filters.regex('^((\d+\.)?(\d+\.)?(\*|\d+)|latest)$'), workflow)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
