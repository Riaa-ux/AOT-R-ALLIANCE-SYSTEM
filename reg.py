import discord
from discord.ext import commands
import aiosqlite
import asyncio
from datetime import datetime

# ---------------- BOT SETUP ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB = "regiment.db"

# ---------------- RANK SYSTEM ----------------
RANK_THRESHOLDS = [0, 100, 300, 700, 1200, 2000, 3500, 5500, 8000, 11000]

# ---------------- FACTIONS ----------------
FACTIONS = {
    "survey": ["Trainee","Cadet","Junior Soldier","Soldier","Scout","Senior Scout","Squad Leader","Captain","Commander","Corps Commander"],
    "garrison": ["Trainee","Cadet","Junior Soldier","Soldier","Guard","Senior Guard","Squad Leader","Section Commander","Chief Officer","Garrison Commander"],
    "mp": ["Trainee","Cadet","Junior Soldier","Soldier","MP Officer","Senior Officer","Inspector","Captain","High Inspector","MP Commander"]
}

# ---------------- SHOP SYSTEM ----------------
SHOP = {
    "vip_role": {"price": 300, "role": "VIP", "type": "permanent"},
    "arxalliance": {"price": 500, "role": "ArxAlliance", "type": "permanent"},

    "2x_giveaway": {"price": 100, "role": "2x Giveaway", "type": "temporary", "duration": 30},
    "3x_giveaway": {"price": 150, "role": "3x Giveaway", "type": "temporary", "duration": 30},
    "4x_giveaway": {"price": 200, "role": "4x Giveaway", "type": "temporary", "duration": 30}
}

# ---------------- DATABASE ----------------
async def setup_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            exp INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            faction TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            reason TEXT,
            admin_id INTEGER,
            date TEXT
        )
        """)
        await db.commit()

@bot.event
async def on_ready():
    await setup_db()
    print(f"{bot.user} is online.")

# ---------------- JOIN ----------------
@bot.command()
async def join(ctx):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"{ctx.author.mention} joined the regiment.")

# ---------------- FACTION ----------------
@bot.command()
async def faction(ctx, choice: str):
    choice = choice.lower()
    if choice not in FACTIONS:
        return await ctx.send("Choose: survey, garrison, mp")

    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET faction = ? WHERE user_id = ?", (choice, ctx.author.id))
        await db.commit()

    await ctx.send(f"{ctx.author.mention} joined **{choice.upper()}**.")

# ---------------- EXP LOGGING ----------------
async def log_exp(user_id, amount, reason, admin_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        INSERT INTO logs(user_id, amount, reason, admin_id, date)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, reason, admin_id, datetime.utcnow().strftime("%Y-%m-%d %H:%M")))
        await db.commit()

# ---------------- ADD EXP ----------------
@bot.command()
async def addexp(ctx, member: discord.Member, amount: int, *, reason="No reason"):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("No permission.")

    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (member.id,))
        await db.execute("UPDATE users SET exp = exp + ? WHERE user_id = ?", (amount, member.id))
        await db.commit()

    await log_exp(member.id, amount, reason, ctx.author.id)
    await update_rank(member)

    await ctx.send(f"{member.mention} gained {amount} EXP.")

# ---------------- REMOVE EXP ----------------
@bot.command()
async def removeexp(ctx, member: discord.Member, amount: int, *, reason="No reason"):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("No permission.")

    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET exp = MAX(exp - ?, 0) WHERE user_id = ?", (amount, member.id))
        await db.commit()

    await log_exp(member.id, -amount, reason, ctx.author.id)
    await update_rank(member)

    await ctx.send(f"{amount} EXP removed from {member.mention}.")

# ---------------- EXP LOG VIEW ----------------
@bot.command()
async def explogs(ctx, member: discord.Member):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("No permission.")

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("""
        SELECT amount, reason, admin_id, date
        FROM logs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """, (member.id,))
        logs = await cursor.fetchall()

    if not logs:
        return await ctx.send("No logs found.")

    desc = ""
    for amount, reason, admin_id, date in logs:
        admin = await bot.fetch_user(admin_id)
        sign = "+" if amount > 0 else ""
        desc += f"{sign}{amount} EXP | {reason} | by {admin.name} | {date}\n"

    await ctx.send(embed=discord.Embed(title=f"EXP Logs - {member.name}", description=desc))

# ---------------- RANK SYSTEM ----------------
def get_rank_index(exp):
    index = 0
    for i, req in enumerate(RANK_THRESHOLDS):
        if exp >= req:
            index = i
    return index

async def update_rank(member):
    guild = member.guild

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT exp, faction FROM users WHERE user_id = ?", (member.id,))
        data = await cursor.fetchone()

    if not data:
        return

    exp, faction = data
    if not faction:
        return

    rank = FACTIONS[faction][get_rank_index(exp)]

    all_roles = sum(FACTIONS.values(), [])
    old_roles = [discord.utils.get(guild.roles, name=r) for r in all_roles]
    old_roles = [r for r in old_roles if r in member.roles]

    new_role = discord.utils.get(guild.roles, name=rank)

    try:
        if old_roles:
            await member.remove_roles(*old_roles)
        if new_role:
            await member.add_roles(new_role)
    except:
        pass

    try:
        await member.send(f"🎖 Promotion: You are now **{rank}**.")
    except:
        pass

# ---------------- PROFILE ----------------
@bot.command()
async def profile(ctx):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT exp, coins, faction FROM users WHERE user_id = ?", (ctx.author.id,))
        data = await cursor.fetchone()

    if not data:
        return await ctx.send("Use !join first.")

    exp, coins, faction = data
    rank = FACTIONS[faction][get_rank_index(exp)] if faction else "None"

    embed = discord.Embed(title=ctx.author.name)
    embed.add_field(name="EXP", value=exp)
    embed.add_field(name="Coins", value=coins)
    embed.add_field(name="Faction", value=faction)
    embed.add_field(name="Rank", value=rank)

    await ctx.send(embed=embed)

# ---------------- LEADERBOARD ----------------
@bot.command()
async def leaderboard(ctx):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT user_id, exp FROM users ORDER BY exp DESC LIMIT 10")
        rows = await cursor.fetchall()

    desc = ""
    for i, (uid, exp) in enumerate(rows, 1):
        user = await bot.fetch_user(uid)
        desc += f"{i}. {user.name} — {exp} EXP\n"

    await ctx.send(embed=discord.Embed(title="Leaderboard", description=desc))

# ---------------- CONVERT EXP TO COINS ----------------
@bot.command()
async def convert(ctx, amount: int):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT exp FROM users WHERE user_id = ?", (ctx.author.id,))
        exp = (await cursor.fetchone())[0]

        if exp < amount:
            return await ctx.send("Not enough EXP.")

        coins = amount // 100
        if coins <= 0:
            return await ctx.send("Minimum 100 EXP.")

        await db.execute("""
        UPDATE users
        SET exp = exp - ?, coins = coins + ?
        WHERE user_id = ?
        """, (amount, coins, ctx.author.id))
        await db.commit()

    await ctx.send(f"Converted {amount} EXP → {coins} coins.")

# ---------------- TEMP ROLE HANDLER ----------------
async def remove_role_later(member, role, days):
    await asyncio.sleep(days * 86400)
    try:
        await member.remove_roles(role)
    except:
        pass

# ---------------- SHOP ----------------
@bot.command()
async def shop(ctx):
    desc = ""
    for item, data in SHOP.items():
        desc += f"{item} — {data['price']} coins\n"

    await ctx.send(embed=discord.Embed(title="Shop", description=desc))

@bot.command()
async def buy(ctx, item: str):
    item = item.lower()

    if item not in SHOP:
        return await ctx.send("Invalid item.")

    data = SHOP[item]

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT coins FROM users WHERE user_id = ?", (ctx.author.id,))
        coins = (await cursor.fetchone())[0]

        if coins < data["price"]:
            return await ctx.send("Not enough coins.")

        await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (data["price"], ctx.author.id))
        await db.commit()

    role = discord.utils.get(ctx.guild.roles, name=data["role"])

    if role:
        await ctx.author.add_roles(role)

        if data["type"] == "temporary":
            bot.loop.create_task(remove_role_later(ctx.author, role, data["duration"]))
            await ctx.send(f"Purchased {data['role']} for {data['duration']} days.")
        else:
            await ctx.send(f"Purchased {data['role']} permanently.")

    else:
        await ctx.send("Role not found.")

# ---------------- RUN BOT ----------------
bot.run("MTQ5ODk5MzYxNDY3ODY1NTA3Nw.GcRb6M.g6rYBfKV98XAdbH-3bqgykAuFZ3kJQo0INxwjY")
