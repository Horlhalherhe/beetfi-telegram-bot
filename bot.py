
import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
import base58

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============
TELEGRAM_BOT_TOKEN = "8221245628:AAEOa-wo-RlTQRm4fsJ8LnkCSAOyfl0A-nY"
CHANNEL_USERNAME = "Beetfi Channel"
CHANNEL_ID = -1003708414002
YOUR_WALLET_ADDRESS = "9YhCFGRiAAPbPHPhkPf1vEGjG8PWBmVVfY7CkcXCpYGj"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
ENTRY_FEE = 10.0
SUBSCRIPTION_DURATION_DAYS = 7
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
# ========================================

# Store users waiting to send transaction hash
awaiting_hash = {}

# Store pending payments
pending_payments = {}

# Store used transaction signatures to prevent reuse
used_transactions = set()

# Store active subscriptions
active_subscriptions = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    try:
        user = update.effective_user
        user_id = user.id
        
        welcome_message = f"""Welcome to BEETFI 🤝

This channel is about smart betting, discipline, and long-term thinking, not guaranteed wins. Betting comes with risk, and losses are part of the game.

Only bet what you can afford to lose. Manage your bankroll, avoid emotions, and never chase losses. If you stay patient and disciplined, you give yourself a real chance over time.

Bet smart. Stay focused. Welcome to BEETFI 🚀

━━━━━━━━━━━━━━━━━━━━

💰 *Weekly Subscription:* {ENTRY_FEE} USDT (Solana Network)
⏰ *Duration:* 7 days

📍 *Payment Address (tap to copy):*
`{YOUR_WALLET_ADDRESS}`

📋 *How to Subscribe:*
1. Tap the address above to copy it
2. Send exactly {ENTRY_FEE} USDT on Solana network
3. Click "Verify Payment" button below
4. Send your transaction hash/signature
5. Get instant access to Beetfi Channel for 7 days

⚠️ *Important:*
• Send USDT on Solana network only (SPL Token)
• Amount must be exactly: {ENTRY_FEE} USDT
• Access expires after 7 days
• You'll be automatically removed if you don't renew

Need help? Use /help"""
        
        keyboard = [[InlineKeyboardButton("✅ Verify Payment", callback_data='verify_payment')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
        
        pending_payments[user_id] = {
            'amount': ENTRY_FEE,
            'timestamp': datetime.now()
        }
        
        logger.info(f"User {user_id} ({user.username}) started the bot")
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text("Sorry, there was an error. Please try again or use /help")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    help_text = f"""🆘 Help Guide - Beetfi Channel Access

How to pay:
1. Open your Solana wallet (Phantom, Solflare, Trust Wallet, etc.)
2. Select USDT (SPL Token) - NOT SOL
3. Send {ENTRY_FEE} USDT to: {YOUR_WALLET_ADDRESS}
4. After sending, copy the transaction signature
5. Return here and click "Verify Payment" button
6. Paste your transaction signature

Finding your transaction signature:
📱 Phantom Wallet:
- Go to Activity/History
- Tap on your USDT transfer
- Copy the signature (long string of characters)

📱 Solflare:
- View Recent Activity
- Click on the transaction
- Copy transaction signature

🌐 Solscan.io:
- Go to solscan.io
- Search your wallet address
- Find the USDT transfer to our address
- Copy the signature

Commands:
/start - Start the bot and get payment info
/verify <signature> - Verify your payment (alternative method)
/help - Show this help message

Common Issues:
❌ Sent SOL instead of USDT → Must send USDT token
❌ Sent on Ethereum network → Must use Solana network
❌ Wrong amount → Must send exactly {ENTRY_FEE} USDT
❌ Transaction not confirmed → Wait 10-30 seconds and try again

✅ Once verified, you'll get instant access to {CHANNEL_USERNAME}!"""
    
    await update.message.reply_text(help_text)


async def verify_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /verify command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    
    if user_id not in pending_payments:
        await update.message.reply_text("⚠️ Please use /start first to get payment instructions.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide the transaction signature.\n\n"
            "Usage: /verify <transaction_signature>\n\n"
            "Example:\n"
            "/verify 5vK7Jq3mP8nR2wX9cY4bD1fG6hT8sL3kM9vN2xC7zB4aE1qW3rY5uI8oP2aSdFgHjKlZxCvBnM"
        )
        return
    
    tx_signature = context.args[0]
    
    if tx_signature in used_transactions:
        await update.message.reply_text(
            "❌ This transaction has already been used for verification.\n\n"
            "Each transaction can only be used once. Please make a new payment to get access."
        )
        logger.warning(f"User {user_id} attempted to reuse transaction: {tx_signature}")
        return
    
    await update.message.reply_text("🔍 Verifying your payment on Solana blockchain... Please wait.")
    
    logger.info(f"User {user_id} ({username}) attempting verification with tx: {tx_signature}")
    
    try:
        is_valid = await verify_solana_transaction(tx_signature, ENTRY_FEE)
        
        if is_valid:
            invite_link = await generate_invite_link(context)
            
            if invite_link:
                used_transactions.add(tx_signature)
                del pending_payments[user_id]
                
                active_subscriptions[user_id] = {
                    'join_date': datetime.now(),
                    'telegram_user_id': user_id
                }
                
                success_message = f"""✅ Payment Verified Successfully!

Your payment of {ENTRY_FEE} USDT has been confirmed on the Solana blockchain.

🎉 Here's your exclusive invite link to {CHANNEL_USERNAME}:

{invite_link}

⚠️ Important Notes:
- This link can only be used ONCE
- The link will expire after you join
- Access is valid for 7 DAYS from now
- You will be automatically removed after 7 days if you don't renew
- Remember to renew before your subscription expires!

Welcome to Beetfi! 🚀

Enjoy your access to exclusive content and community!"""
                await update.message.reply_text(success_message)
                logger.info(f"✅ Payment verified for user {user_id} ({username}), invite link sent. TX: {tx_signature}")
            else:
                await update.message.reply_text(
                    "❌ Payment verified but error generating invite link.\n\n"
                    "Please contact support with your transaction signature."
                )
                logger.error(f"Failed to generate invite link for verified payment. User: {user_id}, TX: {tx_signature}")
        else:
            await update.message.reply_text(
                f"❌ Payment Verification Failed\n\n"
                f"We couldn't verify your payment. Please ensure:\n\n"
                f"✅ You sent exactly {ENTRY_FEE} USDT (not SOL)\n"
                f"✅ Sent to: {YOUR_WALLET_ADDRESS}\n"
                f"✅ Used Solana network (not Ethereum)\n"
                f"✅ Transaction is confirmed (wait 10-30 seconds)\n"
                f"✅ Transaction signature is correct\n\n"
                f"Try the /verify command again with the correct signature.\n"
                f"Need help? Use /help"
            )
            logger.warning(f"Payment verification failed for user {user_id}. TX: {tx_signature}")
    
    except Exception as e:
        logger.error(f"Error verifying payment for user {user_id}: {e}")
        await update.message.reply_text(
            f"❌ Error verifying transaction\n\n"
            f"There was an error checking your transaction. Please:\n"
            f"1. Verify the signature is correct\n"
            f"2. Wait a minute for blockchain confirmation\n"
            f"3. Try again\n\n"
            f"If the problem persists, contact support.\n\n"
            f"Error details: {str(e)[:100]}"
        )


async def verify_solana_transaction(tx_signature: str, expected_amount: float) -> bool:
    """Verify a Solana transaction"""
    try:
        client = AsyncClient(SOLANA_RPC_URL)
        
        logger.info(f"Checking transaction: {tx_signature}")
        
        try:
            sig = Signature.from_string(tx_signature)
        except Exception as e:
            logger.error(f"Invalid signature format: {e}")
            await client.close()
            return False
        
        response = await client.get_transaction(
            sig,
            encoding="jsonParsed",
            max_supported_transaction_version=0
        )
        
        if not response.value:
            logger.warning(f"Transaction not found: {tx_signature}")
            await client.close()
            return False
        
        tx = response.value.transaction
        meta = response.value.transaction.meta
        
        if meta.err:
            logger.warning(f"Transaction failed on blockchain: {tx_signature}")
            await client.close()
            return False
        
        logger.info(f"Transaction found and successful")
        
        if hasattr(meta, 'post_token_balances') and meta.post_token_balances:
            logger.info(f"Found {len(meta.post_token_balances)} post token balances")
            
            if hasattr(meta, 'pre_token_balances') and meta.pre_token_balances:
                for i, post_balance in enumerate(meta.post_token_balances):
                    if i < len(meta.pre_token_balances):
                        pre_balance = meta.pre_token_balances[i]
                        
                        if hasattr(post_balance, 'ui_token_amount') and hasattr(pre_balance, 'ui_token_amount'):
                            post_amount = float(post_balance.ui_token_amount.ui_amount or 0)
                            pre_amount = float(pre_balance.ui_token_amount.ui_amount or 0)
                            transferred = abs(post_amount - pre_amount)
                            
                            logger.info(f"Balance change detected: {transferred} tokens")
                            
                            if transferred >= expected_amount * 0.99:
                                logger.info(f"✅ Valid payment found: {transferred} USDT in tx {tx_signature}")
                                await client.close()
                                return True
        
        instructions = tx.transaction.message.instructions
        
        logger.info(f"Checking {len(instructions)} instructions")
        
        for idx, instruction in enumerate(instructions):
            logger.info(f"Instruction {idx}: {type(instruction)}")
            
            if hasattr(instruction, 'parsed'):
                parsed = instruction.parsed
                logger.info(f"Parsed instruction type: {parsed.get('type')}")
                
                if parsed.get('type') in ['transfer', 'transferChecked']:
                    info = parsed.get('info', {})
                    
                    if 'tokenAmount' in info:
                        amount = float(info['tokenAmount'].get('uiAmount', 0))
                    elif 'amount' in info:
                        amount = float(info.get('amount', 0)) / 1_000_000
                    else:
                        continue
                    
                    logger.info(f"Found transfer of {amount} tokens")
                    
                    if amount >= expected_amount * 0.99:
                        logger.info(f"✅ Valid payment found: {amount} USDT in tx {tx_signature}")
                        await client.close()
                        return True
        
        await client.close()
        logger.warning(f"No matching USDT transfer of {expected_amount} found in tx: {tx_signature}")
        return False
        
    except Exception as e:
        logger.error(f"Error verifying Solana transaction {tx_signature}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def generate_invite_link(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Generate a one-time invite link for the channel"""
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"Beetfi-Entry-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
        
    except Exception as e:
        logger.error(f"Error generating invite link: {e}")
        logger.error(f"Make sure bot is admin in channel {CHANNEL_ID} with 'Invite Users' permission")
        return None


async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """Check and remove users with expired subscriptions"""
    try:
        current_time = datetime.now()
        expired_users = []
        
        for user_id, sub_info in active_subscriptions.items():
            join_date = sub_info['join_date']
            days_elapsed = (current_time - join_date).days
            
            if days_elapsed >= SUBSCRIPTION_DURATION_DAYS:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            try:
                await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                
                del active_subscriptions[user_id]
                
                logger.info(f"Removed expired user {user_id} from channel")
                
                try:
                    expiry_message = f"""⏰ Subscription Expired

Your 7-day access to {CHANNEL_USERNAME} has ended.

To regain access:
1. Send /start to get payment instructions
2. Make a new payment of {ENTRY_FEE} USDT
3. Verify and get a new invite link

Thank you for being part of Beetfi! 🤝"""
                    
                    await context.bot.send_message(chat_id=user_id, text=expiry_message)
                except Exception as e:
                    logger.warning(f"Could not notify user {user_id} about expiry: {e}")
                    
            except Exception as e:
                logger.error(f"Error removing user {user_id}: {e}")
        
        if expired_users:
            logger.info(f"Checked subscriptions: Removed {len(expired_users)} expired users")
        
    except Exception as e:
        logger.error(f"Error in check_expired_subscriptions: {e}")


async def send_renewal_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Send renewal reminders to users 1 day before expiry"""
    try:
        current_time = datetime.now()
        
        for user_id, sub_info in active_subscriptions.items():
            join_date = sub_info['join_date']
            days_elapsed = (current_time - join_date).days
            
            if days_elapsed == 6:
                try:
                    reminder_message = f"""⚠️ Subscription Expiring Soon!

Your access to {CHANNEL_USERNAME} will expire in 24 hours.

To continue your access:
1. Send /start to get payment instructions
2. Make a payment of {ENTRY_FEE} USDT
3. Verify your payment

Don't lose access to exclusive content! Renew now! 🚀"""
                    
                    await context.bot.send_message(chat_id=user_id, text=reminder_message)
                    logger.info(f"Sent renewal reminder to user {user_id}")
                except Exception as e:
                    logger.warning(f"Could not send reminder to user {user_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Error in send_renewal_reminders: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'verify_payment':
        awaiting_hash[user_id] = True
        
        verify_message = """📝 Payment Verification

Please send your transaction hash/signature now.

💡 How to find your transaction hash:

🔹 Phantom Wallet:
   Tap Activity → Select transaction → Copy signature

🔹 Solflare:
   Recent Activity → Click transaction → Copy signature

🔹 Solscan.io:
   Search your wallet → Find transaction → Copy signature

Just paste the transaction hash here and send it to me!

Example: 5vK7Jq3mP8nR2wX9cY4bD1fG6hT8sL..."""
        await query.edit_message_text(text=verify_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if user_id in awaiting_hash and awaiting_hash[user_id]:
        tx_signature = message_text
        
        if tx_signature in used_transactions:
            await update.message.reply_text(
                "❌ This transaction has already been used for verification.\n\n"
                "Each transaction can only be used once. Please make a new payment to get access."
            )
            logger.warning(f"User {user_id} attempted to reuse transaction: {tx_signature}")
            return
        
        await update.message.reply_text("🔍 Verifying your payment... Please wait.")
        
        logger.info(f"User {user_id} sent transaction hash via message: {tx_signature}")
        
        try:
            is_valid = await verify_solana_transaction(tx_signature, ENTRY_FEE)
            
            if is_valid:
                invite_link = await generate_invite_link(context)
                
                if invite_link:
                    used_transactions.add(tx_signature)
                    
                    if user_id in pending_payments:
                        del pending_payments[user_id]
                    del awaiting_hash[user_id]
                    
                    active_subscriptions[user_id] = {
                        'join_date': datetime.now(),
                        'telegram_user_id': user_id
                    }
                    
                    success_message = f"""✅ Payment Verified Successfully!

Your payment of {ENTRY_FEE} USDT has been confirmed on the Solana blockchain.

🎉 Here's your exclusive invite link to Beetfi Channel:

{invite_link}

⚠️ Important Notes:
- This link can only be used ONCE
- The link will expire after you join
- Access is valid for 7 DAYS from now
- You will be automatically removed after 7 days if you don't renew
- Remember to renew before your subscription expires!

Welcome to Beetfi! 🚀

Enjoy your access to exclusive content and community!"""
                    await update.message.reply_text(success_message)
                    logger.info(f"✅ Payment verified for user {user_id}, invite link sent. TX: {tx_signature}")
                else:
                    await update.message.reply_text(
                        "❌ Payment verified but error generating invite link.\n\n"
                        "Please contact support with your transaction signature."
                    )
                    logger.error(f"Failed to generate invite link for verified payment. User: {user_id}, TX: {tx_signature}")
            else:
                await update.message.reply_text(
                    f"❌ Payment Verification Failed\n\n"
                    f"We couldn't verify your payment. Please ensure:\n\n"
                    f"✅ You sent exactly {ENTRY_FEE} USDT (not SOL)\n"
                    f"✅ Sent to: {YOUR_WALLET_ADDRESS}\n"
                    f"✅ Used Solana network (not Ethereum)\n"
                    f"✅ Transaction is confirmed (wait 10-30 seconds)\n"
                    f"✅ Transaction signature is correct\n\n"
                    f"Click the Verify Payment button again to retry.\n"
                    f"Need help? Use /help"
                )
                logger.warning(f"Payment verification failed for user {user_id}. TX: {tx_signature}")
        
        except Exception as e:
            logger.error(f"Error verifying payment for user {user_id}: {e}")
            await update.message.reply_text(
                f"❌ Error verifying transaction\n\n"
                f"There was an error checking your transaction. Please:\n"
                f"1. Verify the signature is correct\n"
                f"2. Wait a minute for blockchain confirmation\n"
                f"3. Try clicking Verify Payment button again\n\n"
                f"If the problem persists, contact support.\n\n"
                f"Error details: {str(e)[:100]}"
            )
        
        return
    
    await update.message.reply_text(
        "👋 Welcome to Beetfi Access Bot!\n\n"
        "Please use these commands:\n\n"
        "🚀 /start - Get payment instructions\n"
        "✅ /verify <signature> - Verify your payment\n"
        "❓ /help - Get detailed help\n\n"
        f"Weekly access to Beetfi Channel is only {ENTRY_FEE} USDT!"
    )


def main():
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("verify", verify_payment))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    job_queue = application.job_queue
    
    job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=10)
    job_queue.run_repeating(send_renewal_reminders, interval=43200, first=60)
    
    logger.info("=" * 50)
    logger.info("🤖 Beetfi Access Bot Started Successfully!")
    logger.info(f"📢 Channel: {CHANNEL_USERNAME}")
    logger.info(f"💰 Entry Fee: {ENTRY_FEE} USDT")
    logger.info(f"⏰ Subscription: {SUBSCRIPTION_DURATION_DAYS} days")
    logger.info(f"🔐 Wallet: {YOUR_WALLET_ADDRESS}")
    logger.info("🔄 Auto-removal enabled: Checking every hour")
    logger.info("📬 Renewal reminders enabled: Sending twice daily")
    logger.info("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
