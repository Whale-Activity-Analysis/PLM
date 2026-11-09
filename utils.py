import discord
from discord import app_commands
import requests
import json
import os
import re
import time
import asyncio
import logging

logger = logging.getLogger(__name__)

"""
Load correct env
"""
def currentFolder():
  # Aktuellen Ordner Basename extrahieren
  return os.path.basename(os.getcwd())

def loadEnv():
  env_file_name = "env.json" if currentFolder() == "BMM" else "envtest.json"
  
  # Env laden
  with open(f"data/{env_file_name}", "r") as f:
    envData = json.load(f)
  return envData
  
envData = loadEnv()

# Helper-Funktionen
def simplify(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', name.upper())
  

def getPlayerForBsId(bs_id):
  bs_id = bs_id.upper().replace(" ", "").replace("#", "")
  url = f"https://api.brawlstars.com/v1/players/%23{bs_id}"
  headers = {
      "Authorization": f"Bearer {envData['BsApi']}"
  }
  try:
    response = requests.get(url, headers=headers, timeout=3)
  except requests.RequestException as error:
    logger.warning("Brawl Stars player lookup failed: tag=%s error=%s", bs_id, type(error).__name__)
    return None, bs_id, True

  try:
    player = response.json()
  except ValueError:
    logger.warning("Brawl Stars player lookup returned invalid JSON: tag=%s status=%s", bs_id, response.status_code)
    return None, bs_id, True

  reason = player.get("reason") if isinstance(player, dict) else None
  if response.status_code == 200 and isinstance(player, dict) and player.get("tag") and not reason:
    return player, bs_id, False
  if response.status_code == 404 and reason == "notFound":
    return None, bs_id, False

  logger.warning("Brawl Stars player lookup rejected: tag=%s status=%s reason=%r", bs_id, response.status_code, str(reason)[:128])
  return None, bs_id, True
    
      
async def fetchBattleLog(bs_id):
  bs_id = bs_id.replace("#", "")
  url = f"https://api.brawlstars.com/v1/players/%23{bs_id}/battlelog"
  headers = {
      "Authorization": f"Bearer {envData['BsApi']}"
  }
  try:
    response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
    if response.status_code == 200:
      return response.json().get("items")
  except Exception:
    return None

# -----------------------------------------------------------------------------------------------------------------------

# View Klasse zum Anzeigen der Items wie Buttons und Auswahllisten
class View(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        for item in items:
            self.add_item(item)

# LinkButton Klasse
class LinkButton(discord.ui.Button):
  def __init__(self, label, url, emoji=None):
    super().__init__(label=label, style=discord.ButtonStyle.link, url=url, emoji=emoji)


def dynamic_guild_cooldown(seconds: int = 15, bot_owner_id: int = 324607583841419276, use_matchmaking_setting: bool = False):
  cooldowns = {}

  async def predicate(interaction: discord.Interaction) -> bool:
    if interaction.user.id == bot_owner_id:
      return True

    cooldown_duration = seconds
    if use_matchmaking_setting and interaction.guild:
      import mongodb
      guild_options = await asyncio.to_thread(mongodb.findGuildOptions, interaction.guild.id)
      if guild_options:
        cooldown_duration = guild_options.get("cooldown_mm", 120)

    guild_id = interaction.guild.id if interaction.guild else 0
    key = (guild_id, interaction.user.id)
    current_time = time.time()

    if key in cooldowns:
      time_passed = current_time - cooldowns[key]
      if time_passed < cooldown_duration:
        retry_after = cooldown_duration - time_passed
        raise app_commands.CommandOnCooldown(None, retry_after)

    cooldowns[key] = current_time
    return True

  return app_commands.check(predicate)