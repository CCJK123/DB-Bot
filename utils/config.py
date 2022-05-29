import os

token: str = os.environ['MYSQLCONNSTR_BOT_TOKEN']
timeout: float = 300

resource_emojis = {
    'money': '<:money:943807961778765835>',
    'food': '<:food:943805731994476605>',
    'coal': '<:coal:943805934495498241>',
    'oil': '<:oil:943805951406919711>',
    'uranium': '<:uranium:943805874185601024>',
    'lead': '<:lead:943805860218552330>',
    'iron': '<:iron:943805845513330708>',
    'bauxite': '<:bauxite:943805819940659260>',
    'gasoline': '<:gasoline:943805790567952405>',
    'munitions': '<:munitions:943805807441625089>',
    'steel': '<:steel:943805758263414795>',
    'aluminum': '<:aluminum:943805716001603615>',
    'credits': '<:credits:943805742790631474>'
}

guild_id: int = 321984630720954379
guild_ids: list[int] = [guild_id, 941590062540414987]
member_role_id: int = 322071813469241344
staff_role_id: int = 383815082473291778  # unused
gov_role_id: int = 595155137274839040  # unused
bank_gov_role_id: int = 490527202643935234  # unused
on_accepted_added_roles: tuple[int, ...] = (member_role_id, 540341927191642131, 362266182663012393)

api_key: str = os.environ['MYSQLCONNSTR_API_KEY']
bot_key: str = os.environ['MYSQLCONNSTR_BOT_KEY']
offshore_api_key = os.environ['MYSQLCONNSTR_OFFSHORE_API_KEY']
database_url: str = os.environ['MYSQLCONNSTR_DB_URL']
alliance_id: str = '4221'
alliance_name: str = 'Dark Brotherhood'

interviewer_role_id = 331571201686372356
interview_questions = (
    '1. Why do you want to join the Dark Brotherhood? Have you been in another alliance?',
    "2. What's your nation link and leader name?",
    "3. What's your timezone and first language?",
    '4. We as an alliance have high standards for activity. How often will you be able to log in?',
    '5. We believe that security of information is essential to sustainable operation. '
    'Do you promise not to leak information that will harm the well-being of the Dark Brotherhood '
    'or any of its associates?',
    '6. The Dark Brotherhood offers loans and grants for cities, projects and more, '
    'what do you think about paying them back?',
    '7. How do you feel about being called to defend and fight for your alliance at some point?',
    '8. How do you feel about potentially having to sacrifice your infrastructure fighting a losing war for '
    'the sake of doing the right thing?',
    '9. If two superiors of equal rank gave you conflicting orders, what would you do?',
    '10. What skills, knowledge and values can you bring to the alliance?',
    '11. Would you be interested in working in any of the following areas? '
    '(1) Internal Affairs (2) Foreign Affairs (3) Military Affairs (4) Finance. '
    'Remember that it is important to help your fellow members.\n\n'
    'Internal Affairs\n'
    '- Enlist and interview people\n'
    '- Enrich new initiates with the basics of the game\n'
    '- Engage the alliance with fun and games\n'
    '\n'
    'Foreign Affairs\n'
    '- Set up embassies\n'
    '- Be diplomats\n'
    '- Much more\n'
    '\n'
    'Military\n'
    "- Make sure everyone's military is up to code (MMR or Minimum Military Requirement)\n"
    '- Help plan wars, counters and raids.\n'
    '\n'
    'Finance\n'
    '- Manage resources, money, grant loans',
    '12. Do you have any questions or anything else you want to tell us?'
)
interview_sendoff = ('Thank you for answering our questions. An interviewer will be reviewing your answers '
                     'and will get back to you as soon as possible (1 - 4 hours). '
                     'They will respond to your queries and may ask follow up questions.')
