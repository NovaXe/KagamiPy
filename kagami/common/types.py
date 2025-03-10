import discord

type MessageableChannel = discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread | discord.DMChannel | discord.PartialMessageable
type MessageableGuildChannel = discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread
