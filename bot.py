import discord
from discord.ext import commands
from discord import app_commands
from google import genai
import subprocess
import tempfile
import os
import sys
import asyncio
import threading
import time

# -----------------------------------------
# CONFIG - set these as Environment Variables on Render
# -----------------------------------------
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TEST_GUILD_ID = int(os.environ.get('TEST_GUILD_ID'))
YOUR_USER_ID = int(os.environ.get('YOUR_USER_ID'))

# -----------------------------------------
# Gemini Setup
# -----------------------------------------
client = genai.Client(api_key=GEMINI_API_KEY)
SYSTEM_PROMPT = 'You are codeAi, an expert programming assistant in a Discord server. Give clear, concise answers with code examples in markdown code blocks.'
print('🤖 Gemini AI ready.')

# -----------------------------------------
# Setup
# -----------------------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
guild = discord.Object(id=TEST_GUILD_ID)

# -----------------------------------------
# Timeout Warning (optional, not needed on Render)
# -----------------------------------------
async def warn_before_timeout():
    await asyncio.sleep(11 * 3600 + 50 * 60)
    try:
        user = await bot.fetch_user(YOUR_USER_ID)
        await user.send('⚠️ **codeAi Warning!**\nBot restarting soon! 🔄')
    except Exception as e:
        print(f'Could not send DM: {e}')

# -----------------------------------------
# Helpers
# -----------------------------------------
async def ask_gemini(prompt):
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f'{SYSTEM_PROMPT}\n\n{prompt}'
            )
        )
        return response.text
    except Exception as e:
        print(f'Gemini error: {e}')
        return f'❌ AI error: {str(e)}'

def run_code(code, language):
    ext_map = {'python': 'py', 'javascript': 'js', 'bash': 'sh'}
    ext = ext_map.get(language.lower(), 'txt')
    with tempfile.NamedTemporaryFile(suffix=f'.{ext}', mode='w', delete=False) as f:
        f.write(code)
        fname = f.name
    try:
        cmd_map = {
            'python': [sys.executable, fname],
            'javascript': ['node', fname],
            'bash': ['bash', fname]
        }
        cmd = cmd_map.get(language.lower())
        if not cmd:
            return f'❌ Language `{language}` not supported.'
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (result.stdout or result.stderr or '(no output)')[:1800]
    except subprocess.TimeoutExpired:
        return '⏱️ Code timed out after 5 seconds.'
    except FileNotFoundError:
        return f'❌ Runtime for `{language}` not found.'
    finally:
        os.unlink(fname)

def chunk_message(text, limit=1900):
    return [text[i:i+limit] for i in range(0, len(text), limit)]

# -----------------------------------------
# Events
# -----------------------------------------
@bot.event
async def on_ready():
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f'✅ codeAi online as {bot.user}')
    try:
        user = await bot.fetch_user(YOUR_USER_ID)
        await user.send('✅ **codeAi is online!**\nRunning 24/7 on Render 🚀')
    except Exception as e:
        print(f'Could not send startup DM: {e}')

# -----------------------------------------
# Slash Commands
# -----------------------------------------
@bot.tree.command(name='ask', description='Ask codeAi a coding question', guild=guild)
@app_commands.describe(question='Your coding question')
async def slash_ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    answer = await ask_gemini(question)
    for chunk in chunk_message(answer):
        await interaction.followup.send(chunk)

@bot.tree.command(name='run', description='Run a code snippet', guild=guild)
@app_commands.describe(language='python, javascript, or bash', code='The code to run')
async def slash_run(interaction: discord.Interaction, language: str, code: str):
    await interaction.response.defer(thinking=True)
    output = run_code(code, language)
    await interaction.followup.send(f'**▶ Output ({language}):**\n```\n{output}\n```')

@bot.tree.command(name='review', description='Get a code review', guild=guild)
@app_commands.describe(code='Code to review')
async def slash_review(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True)
    prompt = f'Review this code for bugs, performance, and best practices. Use: ✅ Strengths, ⚠️ Issues, 💡 Suggestions.\n```\n{code}\n```'
    review = await ask_gemini(prompt)
    for chunk in chunk_message(review):
        await interaction.followup.send(chunk)

@bot.tree.command(name='explain', description='Explain what code does', guild=guild)
@app_commands.describe(code='Code to explain')
async def slash_explain(interaction: discord.Interaction, code: str):
    await interaction.response.defer(thinking=True)
    prompt = f'Explain this code in plain English, beginner-friendly, with bullet points.\n```\n{code}\n```'
    explanation = await ask_gemini(prompt)
    for chunk in chunk_message(explanation):
        await interaction.followup.send(chunk)

@bot.tree.command(name='fix', description='Find and fix bugs in code', guild=guild)
@app_commands.describe(code='Buggy code', error='Optional error message')
async def slash_fix(interaction: discord.Interaction, code: str, error: str = ''):
    await interaction.response.defer(thinking=True)
    prompt = f'Find and fix the bug(s). Explain what went wrong and show the fixed code.\n```\n{code}\n```'
    if error:
        prompt += f'\n\nError:\n```\n{error}\n```'
    fix = await ask_gemini(prompt)
    for chunk in chunk_message(fix):
        await interaction.followup.send(chunk)

@bot.tree.command(name='help', description='Show all codeAi commands', guild=guild)
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title='🤖 codeAi — Commands', color=discord.Color.blurple())
    cmds = {
        '/ask [question]': 'Ask a coding question',
        '/run [language] [code]': 'Run Python, JS, or Bash',
        '/review [code]': 'Get a code review',
        '/explain [code]': 'Explain what code does',
        '/fix [code] (error)': 'Debug and fix code',
        '/help': 'Show this menu'
    }
    for cmd, desc in cmds.items():
        embed.add_field(name=f'`{cmd}`', value=desc, inline=False)
    embed.set_footer(text='Powered by Google Gemini 2.5 Flash')
    await interaction.response.send_message(embed=embed)

# -----------------------------------------
# Run
# -----------------------------------------
bot.run(DISCORD_TOKEN)
