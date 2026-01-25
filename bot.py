import os
import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from solders.pubkey import Pubkey
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
CHANNEL_USERNAME = "@beetfi"
CHANNEL_ID = -1001003708414002  # Added -100 prefix for supergroup/channel
YOUR_WALLET_ADDRESS = "9YhCFGRiAAPbPHPhkPf1vEGjG8PWBmVVfY7CkcXCpYGj"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"  # USDT SPL Token on Solana
ENTRY_FEE = 10.0  # 10 USDT per month
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"  # Consider upgrading to dedicated RPC for better performance
# ========================================

# Store pending payments: {user_id: {'amount': float, 'timestamp': datetime}}
pending_payments = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    user = update.effective_user
    user_id = user.id
    
    welcome_message = f"""
Welcome to BEETFI 🤝

This channel is about smart betting, discipline, and long-term thinking, not guaranteed wins. Betting comes with risk, and losses are part of the game.

Only bet what you can afford to lose. Manage your bankroll, avoid emotions, and never chase losses. If you stay patient and disciplined, you give yourself a real chance over time.

Bet smart. Stay focused. Welcome to BEETFI 🚀

━━━━━━━━━━━━━━━━━━━━

💰 **Monthly Subscription:** {ENTRY_FEE} USDT (Solana Network)

📍 **Payment Address:**
`{YOUR_WALLET_ADDRESS}`

📋 **How to Subscribe:**
1. Click the **"Subscribe Now"** button below
2. Send exactly **{ENTRY_FEE} USDT** on Solana network to the address above
3. Copy the transaction signature after sending
4. Use: /verify <transaction_signature>
5. Get instant access to {CHANNEL_USERNAME}

⚠️ **Important:**
- Send USDT on **Solana network only** (SPL Token)
- Amount must be exactly: **{ENTRY_FEE} USDT**
- Keep your transaction signature ready

Need help? Use /help
"""
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = [
        [InlineKeyboardButton("💳 Subscribe Now", callback_data='subscribe')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    # Track this user as pending
    pending_payments[user_id] = {
        'amount': ENTRY_FEE,
        'timestamp': datetime.now()
    }
    
    logger.info(f"User {user_id} ({user.username}) started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    help_text = f"""
🆘 **Help Guide - Beetfi Channel Access**

**How to pay:**
1. Open your Solana wallet (Phantom, Solflare, Trust Wallet, etc.)
2. Select USDT (SPL Token) - NOT SOL
3. Send **{ENTRY_FEE} USDT** to: `{YOUR_WALLET_ADDRESS}`
4. After sending, copy the transaction signature
5. Return here and use: /verify <signature>

**Finding your transaction signature:**
📱 **Phantom Wallet:**
- Go to Activity/History
- Tap on your USDT transfer
- Copy the signature (long string of characters)

📱 **Solflare:**
- View Recent Activity
- Click on the transaction
- Copy transaction signature

🌐 **Solscan.io:**
- Go to solscan.io
- Search your wallet address
- Find the USDT transfer to our address
- Copy the signature

**Commands:**
/start - Start the bot and get payment info
/verify <signature> - Verify your payment
/help - Show this help message

**Common Issues:**
❌ Sent SOL instead of USDT → Must send USDT token
❌ Sent on Ethereum network → Must use Solana network
❌ Wrong amount → Must send exactly {ENTRY_FEE} USDT
❌ Transaction not confirmed → Wait 10-30 seconds and try again

**Example:**
`/verify 5vK7Jq3mP8nR2wX9cY4bD1fG6hT8sL3kM9vN2xC7zB4aE1qW3rY5uI8oP2aSdFgHjKlZxCvBnM`

✅ Once verified, you'll get instant access to {CHANNEL_USERNAME}!
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def verify_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /verify command"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    
    # Check if user has started the bot
    if user_id not in pending_payments:
        await update.message.reply_text(
            "⚠️ Please use /start first to get payment instructions."
        )
        return
    
    # Check if signature was provided
    if not context.args:
        await update.message.reply_text(
            "⚠️ Please provide the transaction signature.\n\n"
            "**Usage:** `/verify <transaction_signature>`\n\n"
            "**Example:**\n"
            "`/verify 5vK7Jq3mP8nR2wX9cY4bD1fG6hT8sL3kM9vN2xC7zB4aE1qW3rY5uI8oP2aSdFgHjKlZxCvBnM`",
            parse_mode='Markdown'
        )
        return
    
    tx_signature = context.args[0]
    
    await update.message.reply_text("🔍 Verifying your payment on Solana blockchain... Please wait.")
    
    logger.info(f"User {user_id} ({username}) attempting verification with tx: {tx_signature}")
    
    try:
        # Verify the transaction
        is_valid = await verify_solana_transaction(tx_signature, ENTRY_FEE)
        
        if is_valid:
            # Generate invite link
            invite_link = await generate_invite_link(context)
            
            if invite_link:
                # Remove from pending
                del pending_payments[user_id]
                
                success_message = f"""
✅ **Payment Verified Successfully!**

Your payment of {ENTRY_FEE} USDT has been confirmed on the Solana blockchain.

🎉 **Here's your exclusive invite link to {CHANNEL_USERNAME}:**

{invite_link}

⚠️ **Important Notes:**
- This link can only be used **ONCE**
- The link will expire after you join
- This is valid for 1 month of access
- Save any important content from the channel

**Welcome to Beetfi!** 🚀

Enjoy your access to exclusive content and community!
"""
                await update.message.reply_text(success_message, parse_mode='Markdown')
                logger.info(f"✅ Payment verified for user {user_id} ({username}), invite link sent. TX: {tx_signature}")
            else:
                await update.message.reply_text(
                    "❌ Payment verified but error generating invite link.\n\n"
                    "Please contact support with your transaction signature."
                )
                logger.error(f"Failed to generate invite link for verified payment. User: {user_id}, TX: {tx_signature}")
        else:
            await update.message.reply_text(
                f"❌ **Payment Verification Failed**\n\n"
                f"We couldn't verify your payment. Please ensure:\n\n"
                f"✅ You sent exactly **{ENTRY_FEE} USDT** (not SOL)\n"
                f"✅ Sent to: `{YOUR_WALLET_ADDRESS}`\n"
                f"✅ Used **Solana network** (not Ethereum)\n"
                f"✅ Transaction is confirmed (wait 10-30 seconds)\n"
                f"✅ Transaction signature is correct\n\n"
                f"Try the /verify command again with the correct signature.\n"
                f"Need help? Use /help",
                parse_mode='Markdown'
            )
            logger.warning(f"Payment verification failed for user {user_id}. TX: {tx_signature}")
    
    except Exception as e:
        logger.error(f"Error verifying payment for user {user_id}: {e}")
        await update.message.reply_text(
            f"❌ **Error verifying transaction**\n\n"
            f"There was an error checking your transaction. Please:\n"
            f"1. Verify the signature is correct\n"
            f"2. Wait a minute for blockchain confirmation\n"
            f"3. Try again\n\n"
            f"If the problem persists, contact support.\n\n"
            f"Error details: `{str(e)[:100]}`",
            parse_mode='Markdown'
        )


async def verify_solana_transaction(tx_signature: str, expected_amount: float) -> bool:
    """
    Verify a Solana transaction
    Returns True if transaction is valid and amount matches
    """
    try:
        client = AsyncClient(SOLANA_RPC_URL)
        
        logger.info(f"Checking transaction: {tx_signature}")
        
        # Get transaction details
        response = await client.get_transaction(
            tx_signature,
            encoding="jsonParsed",
            max_supported_transaction_version=0
        )
        
        if not response.value:
            logger.warning(f"Transaction not found: {tx_signature}")
            await client.close()
            return False
        
        tx = response.value.transaction
        meta = response.value.transaction.meta
        
        # Check if transaction was successful
        if meta.err:
            logger.warning(f"Transaction failed on blockchain: {tx_signature}")
            await client.close()
            return False
        
        # Parse the transaction to find USDT transfer
        instructions = tx.transaction.message.instructions
        
        for instruction in instructions:
            # Look for SPL token transfer instruction
            if hasattr(instruction, 'parsed'):
                parsed = instruction.parsed
                
                if parsed.get('type') == 'transfer' or parsed.get('type') == 'transferChecked':
                    info = parsed.get('info', {})
                    
                    # Get amount (handle both transfer and transferChecked)
                    if 'tokenAmount' in info:
                        amount = float(info['tokenAmount'].get('uiAmount', 0))
                    else:
                        amount = float(info.get('amount', 0)) / 1_000_000  # USDT has 6 decimals
                    
                    # Check if amount matches (allow small variance for fees)
                    if amount >= expected_amount * 0.99:  # 1% tolerance
                        logger.info(f"✅ Valid payment found: {amount} USDT in tx {tx_signature}")
                        await client.close()
                        return True
        
        await client.close()
        logger.warning(f"No matching USDT transfer found in tx: {tx_signature}")
        return False
        
    except Exception as e:
        logger.error(f"Error verifying Solana transaction {tx_signature}: {e}")
        return False


async def generate_invite_link(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Generate a one-time invite link for the channel"""
    try:
        # Create invite link that can only be used by 1 person
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,  # One-time use
            name=f"Beetfi-Entry-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        
        logger.info(f"Generated invite link: {invite_link.invite_link}")
        return invite_link.invite_link
        
    except Exception as e:
        logger.error(f"Error generating invite link: {e}")
        logger.error(f"Make sure bot is admin in channel {CHANNEL_ID} with 'Invite Users' permission")
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    await update.message.reply_text(
        "👋 **Welcome to Beetfi Access Bot!**\n\n"
        "Please use these commands:\n\n"
        "🚀 /start - Get payment instructions\n"
        "✅ /verify <signature> - Verify your payment\n"
        "❓ /help - Get detailed help\n\n"
        f"Monthly access to {CHANNEL_USERNAME} is only **{ENTRY_FEE} USDT**!",
        parse_mode='Markdown'
    )


def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("verify", verify_payment))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("=" * 50)
    logger.info("🤖 Beetfi Access Bot Started Successfully!")
    logger.info(f"📢 Channel: {CHANNEL_USERNAME}")
    logger.info(f"💰 Entry Fee: {ENTRY_FEE} USDT")
    logger.info(f"🔐 Wallet: {YOUR_WALLET_ADDRESS}")
    logger.info("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()