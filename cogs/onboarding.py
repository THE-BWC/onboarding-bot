import discord
from discord.ext import commands
from discord.ui import View, Button, Select
import config
from utils import log_error

class OnboardingView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.answers = {}
        self.step = 0
        self.questions = [
            "rules",
            "sop",
            "reason",
            "game"
        ]

    # Step 1: Rules
    @discord.ui.button(label="Yes, I have read the rules", style=discord.ButtonStyle.green, custom_id="rules_yes")
    async def rules_yes(self, interaction: discord.Interaction, button: Button):
        self.answers["rules"] = "Yes"
        self.clear_items()
        
        # Next Step: SOP
        sop_yes = Button(label="Yes, I understand", style=discord.ButtonStyle.green, custom_id="sop_yes")
        sop_yes.callback = self.sop_yes
        
        sop_no = Button(label="No / Need Help", style=discord.ButtonStyle.red, custom_id="sop_no")
        sop_no.callback = self.sop_no
        
        self.add_item(sop_yes)
        self.add_item(sop_no)
        
        await interaction.response.edit_message(content="📘 **Standard Operating Procedure (SOP)**\nDo you understand the SOP?", view=self)

    # Step 2: SOP
    async def sop_yes(self, interaction: discord.Interaction):
        self.answers["sop"] = "Yes"
        self.clear_items()
        self.add_reason_buttons()
        await interaction.response.edit_message(content="🎯 **Reason for Joining**\nAre you joining to play games or as a guest?", view=self)

    async def sop_no(self, interaction: discord.Interaction):
         await interaction.response.send_message("❌ Please read the SOP channel again or ask an admin for clarification before proceeding.", ephemeral=True)

    def add_reason_buttons(self):
        btn_game = Button(label="To Play (Game)", style=discord.ButtonStyle.primary, custom_id="reason_game")
        btn_game.callback = self.reason_game
        
        btn_guest = Button(label="Just Looking (Guest)", style=discord.ButtonStyle.secondary, custom_id="reason_guest")
        btn_guest.callback = self.reason_guest
        
        self.add_item(btn_game)
        self.add_item(btn_guest)

    # Step 3: Reason
    async def reason_game(self, interaction: discord.Interaction):
        self.answers["reason"] = "Game"
        self.clear_items()
        self.add_game_select()
        await interaction.response.edit_message(content="🎮 **Primary Game**\nWhich game are you here for?", view=self)

    async def reason_guest(self, interaction: discord.Interaction):
        self.answers["reason"] = "Guest"
        self.answers["game"] = "None"
        
        role_error = None
        # Assign Guest Role immediately
        guest_role = interaction.guild.get_role(config.GUEST_ROLE_ID)
        if guest_role:
            try:
                await interaction.user.add_roles(guest_role)
            except Exception as e:
                await log_error(e, interaction)
                role_error = "Failed to assign Guest Role (Permission Error)"
        else:
             await log_error(ValueError(f"Guest role not found: {config.GUEST_ROLE_ID}"), interaction)
             role_error = "Guest Role configuration error"

        await self.finish_onboarding(interaction, error_msg=role_error)

    def add_game_select(self):
        # Dynamically create options from config
        options = []
        for label, data in config.GAME_ROLES.items():
            options.append(discord.SelectOption(label=label, value=label, emoji=data["emoji"]))

        select = Select(
            placeholder="Select your game...",
            options=options,
            custom_id="game_select"
        )
        select.callback = self.game_select
        self.add_item(select)

    # Step 4: Game Select
    async def game_select(self, interaction: discord.Interaction):
        self.answers["game"] = interaction.data["values"][0] # type: ignore
        await self.finish_onboarding(interaction)

    # Finish
    async def finish_onboarding(self, interaction: discord.Interaction, error_msg: str = None):
        self.clear_items()
        
        # Assign Role (if not already handled or errored)
        game_label = self.answers.get("game")
        role_id = None
        
        if game_label and game_label != "None":
            if game_label in config.GAME_ROLES:
                role_id = config.GAME_ROLES[game_label]["role_id"]
            
        assigned_role = False
        role_name_display = "Unknown"
        role = None
        
        # Logic: If we haven't failed yet, and we have a role to assign, try it.
        if role_id and not error_msg:
            role = interaction.guild.get_role(role_id)
            guest_role = interaction.guild.get_role(config.GUEST_ROLE_ID)
            
            if role:
                role_name_display = role.name
                roles_to_add = [role]
                
                # Also add Guest role if found
                if guest_role:
                    roles_to_add.append(guest_role)
                else:
                     await log_error(ValueError(f"Guest Role ID not found during Game selection: {config.GUEST_ROLE_ID}"), interaction)
                     # We continue to at least give them the Game role, but log the error
                
                try:
                    await interaction.user.add_roles(*roles_to_add)
                    assigned_role = True
                except Exception as e:
                    await log_error(e, interaction)
                    error_msg = f"Failed to assign roles (**{role.name}**). Please contact an Admin."
            else:
                 # We don't have the role name since we couldn't find it, so use the Label or ID
                 await log_error(ValueError(f"Role ID not found: {role_id} (Game: {game_label})"), interaction)
                 error_msg = f"Role for **{game_label}** not found on server (ID: {role_id}). Please contact an Admin."

        # Log results
        try:
            log_channel = interaction.guild.get_channel(config.JOIN_LOGS_CHANNEL_ID) if interaction.guild else self.bot.get_channel(config.JOIN_LOGS_CHANNEL_ID)
            if log_channel:
                # Create Embed
                embed = discord.Embed(
                    title="📥 Onboarding Complete" if not error_msg else "⚠️ Onboarding Incomplete",
                    color=discord.Color.green() if not error_msg else discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                embed.add_field(name="User", value=f"{interaction.user.mention}\n`{interaction.user.name}`", inline=True)
                embed.add_field(name="Reason", value=self.answers.get('reason'), inline=True)
                embed.add_field(name="Game / Role", value=self.answers.get('game'), inline=True)
                embed.add_field(name="Rules Accepted", value=self.answers.get('rules'), inline=True)
                embed.add_field(name="SOP Understood", value=self.answers.get('sop'), inline=True)
                
                if error_msg:
                    embed.add_field(name="⚠️ Error Warning", value=error_msg, inline=False)
                
                # Ping the Game Role if assigned (Alerts C&S Staff)
                ping_content = role.mention if role and not error_msg else None
                
                await log_channel.send(content=ping_content, embed=embed)
        except Exception as e:
            await log_error(e, interaction)

        # Final Message Construction
        if error_msg:
            final_msg = f"⚠️ **Attention Needed**\nYour onboarding info was saved, but we encountered an issue:\n> {error_msg}\n\nPlease contact a Moderator or Admin for assistance."
        else:
            final_msg = "✅ **You are all set!** Welcome to the server."
            if assigned_role:
                final_msg += f"\nAssigned Role: **{role_name_display}**"
        
        await interaction.response.edit_message(content=final_msg, view=None)


class StartView(View):
    def __init__(self, bot):
        super().__init__(timeout=None) # Persistent view
        self.bot = bot

    @discord.ui.button(label="Start Onboarding", style=discord.ButtonStyle.primary, custom_id="start_onboarding_btn", emoji="👋")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        # 1. Check if user is already onboarded (Guest Role Only)
        # We only check for the Guest Role to allow users with pre-assigned game roles to still onboard if needed.
        if any(role.id == config.GUEST_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message(
                "✅ **You are already onboarded!**\nYou already have the Guest role. If you need to change your game, please check the `#roles` channel or ask a Moderator.",
                ephemeral=True
            )
            return

        # 2. Proceed with Onboarding
        view = OnboardingView(self.bot)
        await interaction.response.send_message(
            "Welcome! Let's get you set up.\n**Have you read the rules?**", 
            view=view, 
            ephemeral=True
        )

class OnboardingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Register persistent view on bot start
        # Note: on_ready can be called multiple times, so Views normally handle unique addition
        self.bot.add_view(StartView(self.bot))
        
        # Ensure Button exists (Optional logic re-added from bot.py)
        if config.START_CHANNEL_ID:
            channel = self.bot.get_channel(config.START_CHANNEL_ID)
            if channel:
                async for msg in channel.history(limit=5):
                    if msg.author == self.bot.user and "Click below" in msg.content:
                       return # Already there
                
                view = StartView(self.bot)
                await channel.send("👋 **Welcome to the Server!**\nClick below to start your onboarding process.", view=view)
            else:
                print(f"Could not find start channel with ID {config.START_CHANNEL_ID}")

async def setup(bot):
    await bot.add_cog(OnboardingCog(bot))
