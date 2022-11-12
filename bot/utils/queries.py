from .pnwutils.api import APIQuery

# mutations
withdrawal_query_text = '''
mutation withdraw(
  $receiver_id: ID!, $receiver_type: Int!, $money: Float,
  $coal: Float, $oil: Float, $uranium: Float, $iron: Float,
  $bauxite: Float, $lead: Float, $gasoline: Float, $munitions: Float,
  $steel: Float, $aluminum: Float, $food: Float, $note: String
) {
    bankWithdraw(
      receiver: $receiver_id, receiver_type: $receiver_type, money: $money,
      coal: $coal, oil: $oil, uranium: $uranium, iron: $iron, bauxite: $bauxite,
      lead: $lead, gasoline: $gasoline, munitions: $munitions, steel: $steel,
      aluminum: $aluminum, food: $food, note: $note
    ) {
        id
    }
}
'''
withdrawal_query = APIQuery(withdrawal_query_text, bot_headers=True, receiver_id=int, receiver_type=int,
                            money=int, food=int, coal=int, oil=int, uranium=int, lead=int, iron=int, bauxite=int,
                            gasoline=int, munitions=int, steel=int, aluminum=int, note=str)
# receiver_type: 1 for nation, 2 for alliance

offshore_info_query_text = '''
query offshore_info {
    me {
        nation {
            alliance_id
        }
    }
}
'''
offshore_info_query = APIQuery(offshore_info_query_text)

# finance.py

finance_nation_info_query_text = '''
query finance_nation_info($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            # Display Request, Withdrawal Link
            nation_name

            # Alliance Check
            alliance_id

            # City Grants, Project Grants & War Aid
            num_cities

            # City Grants & Project Grants 
            urban_planning
            advanced_urban_planning
            metropolitan_planning
            government_support_agency

            # Project Grants
            central_intelligence_agency
            propaganda_bureau

            # Project Grants & War Aid
            center_for_civil_engineering
            advanced_engineering_corps

            # War Aid
            soldiers
            tanks
            aircraft
            ships
            beige_turns
            wars {
                att_id
                turns_left
            }
            cities {
                barracks
                factory
                hangar
                drydock
                name
                infrastructure
            }
            
            domestic_policy
        }
    }
}

'''
finance_nation_info_query = APIQuery(finance_nation_info_query_text, nation_id=int)

# bank.py
resources_fragment = '''
fragment resources on Bankrec {
    money
    coal
    oil
    uranium
    iron
    bauxite
    lead
    gasoline
    munitions
    steel
    aluminum
    food
}
'''

bank_transactions_query_text = '''
query bank_transactions($alliance_id: [Int]) {
    alliances(id: $alliance_id, first: 1) {
        data {
            bankrecs {
                sender_id
                sender_type
                recipient_id
                recipient_type
                date
                ...resources
            }
        }
    }
}
''' + resources_fragment
bank_transactions_query = APIQuery(bank_transactions_query_text, alliance_id=int)

# some notes on the format of this data
# id: unique id of this transaction
# sid: id of the sender
# stype: type of the sender
#  - 1: nation
#  - 2: alliance
# rid: id of the receiver
# rtype: type of receiver
#  numbers mean the same as in stype
# pid: id of the banker (the person who initiated this transaction)
# note that if stype is 1 then rtype is 2 and if rtype is 1 then stype is 2
# but converse is not true due to the existence of inter-alliance transactions
# if stype/rtype is 2 then sid/rid is definitely the alliance id unless both stype/rtype is 2

bank_revenue_query_text = '''
query bank_revenue_query($alliance_id: [Int]) {
    alliances(id: $alliance_id) {
        data {
            taxrecs(orderBy: {column: DATE, order: DESC}) {
                date
                ...resources
            }
        }
    }
}
''' + resources_fragment
bank_revenue_query = APIQuery(bank_revenue_query_text, alliance_id=int)

nation_name_query_text = '''
query nation_name($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            nation_name
        }
    }
}
'''
nation_name_query = APIQuery(nation_name_query_text, nation_id=int)

bank_info_query_text = '''
query bank_info($alliance_id: [Int]) {
    alliances(id: $alliance_id, first: 1) {
        data {
            money
            food
            aluminum
            steel
            munitions
            gasoline
            bauxite
            iron
            lead
            uranium
            oil
            coal
        }
    }
}
'''
bank_info_query = APIQuery(bank_info_query_text, alliance_id=int)

alliance_name_query_text = '''
query alliance_name($alliance_id: [Int]) {
    alliances(id: $alliance_id, first: 1) {
        data {
            name
        }
    }
}
'''
alliance_name_query = APIQuery(alliance_name_query_text, alliance_id=int)

nation_resources_query_text = '''
query nation_resources($nation_id: [Int]) {
    nations(id: $nation_id) {
        data {
            nation_name
            money
            coal
            oil
            uranium
            iron
            bauxite
            lead
            gasoline
            munitions
            steel
            aluminum
            food
        }
    }
}
'''
nation_resources_query = APIQuery(nation_resources_query_text, nation_id=int)

# util.py

nation_register_query_text = '''
query nation_info($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            alliance_id
            discord
        }
    }
}
'''
nation_register_query = APIQuery(nation_register_query_text, nation_id=int)

alliance_member_res_query_text = '''
query alliance_members_res($alliance_id: [Int], $page: Int) {
    nations(alliance_id: $alliance_id, first: 500, page: $page, vmode: false) {
        paginatorInfo {
            hasMorePages
        }
        data {
            alliance_position
            nation_name
            vacation_mode_turns
            id
            food
            uranium
            cities {
                nuclear_power
            }
        }
    }
}
'''
alliance_member_res_query = APIQuery(alliance_member_res_query_text, alliance_id=int)

alliance_activity_query_text = '''
query alliance_activity($alliance_id: [Int], $page: Int) {
    nations(alliance_id: $alliance_id, first: 500, page: $page, vmode: false) {
        paginatorInfo {
            hasMorePages
        }
        data {
            alliance_position
            nation_name
            id
            last_active
        }
    }
}
'''
alliance_activity_query = APIQuery(alliance_activity_query_text, True, alliance_id=int)

nation_info_query_text = '''
query nation_info_query($nation_id: [Int]) {
    nations(id: $nation_id) {
        data {
            nation_name
            war_policy
            domestic_policy
            score
            soldiers
            tanks
            aircraft
            ships
            missiles
            nukes
            wars {
                att_id
                naval_blockade  
                turns_left
            }
        }
    }
}
'''
nation_info_query = APIQuery(nation_info_query_text, nation_id=int)

alliance_tiers_query_text = '''
query nation_discord($alliance_ids: [Int]) {
    alliances(id: $alliance_ids) {
        data {
            nations {
                num_cities
                alliance_position
            }
            name
        }
    }
}
'''
alliance_tiers_query = APIQuery(alliance_tiers_query_text, alliance_ids=[int])

global_trade_prices_query_text = '''
query global_trade_prices {
    trades(type: GLOBAL, accepted: false, first: 1000) {
        data {
            sender_id
            receiver_id
            offer_resource
            buy_or_sell
            price
        }
        paginatorInfo {
            hasMorePages
        }
    }
}
'''
global_trade_prices_query = APIQuery(global_trade_prices_query_text, True)

# war related queries
# both detector.py and war.py

nation_war_data_fragment = '''
fragment nation_data on Nation {
    id
    nation_name
    score
    num_cities
    war_policy
    soldiers
    tanks
    aircraft
    ships
    missiles
    nukes
    alliance_position
    alliance {
        id
        name
    }
}
'''

new_war_query_text = '''
query new_war($war_id: [Int]) {
    wars(id: $war_id, first: 1) {
        data {
            id
            turns_left
            war_type
            att_id
            def_id
            attacker {
                ...new_war_nation_data
            }
            defender {
                ...new_war_nation_data
            }
        }
    }
}

fragment new_war_nation_data on Nation {
    nation_name
    score
    num_cities
    war_policy
    soldiers
    tanks
    aircraft
    ships
    missiles
    nukes
    alliance_position
    alliance {
        id
        name
    }
}
'''
new_war_query = APIQuery(new_war_query_text, war_id=int)

update_war_query_text = '''
query update_war($war_id: [Int]) {
    wars(id: $war_id, first: 1) {
        data {
            id
            date
            winner_id
            turns_left
            war_type
            att_id
            def_id
            att_resistance
            def_resistance
            att_points
            def_points
            attacker {
                ...nation_data
            }
            defender {
                ...nation_data
            }
            attacks(min_id: 0) {
                type
                date
            }
        }
    }
}
''' + nation_war_data_fragment
update_war_query = APIQuery(update_war_query_text, war_id=int)

individual_war_query_text = '''
query individual_war($war_id: [Int]) {
    wars(id: $war_id, active: false) {
        data {
            id
            date
            winner_id
            turns_left
            war_type
            att_id
            def_id
            att_resistance
            def_resistance
            att_points
            def_points
            attacker {
                ...nation_data
                population
            }
            defender {
                ...nation_data
                population
            }
            attacks(min_id: 0) {
                type
                date
            }
        }
    }
}
''' + nation_war_data_fragment
individual_war_query = APIQuery(individual_war_query_text, war_id=int)

nation_active_wars_query_text = '''
query nation_active_wars($nation_id: [Int]) {
    wars(nation_id: $nation_id) {
        data {
            id
            date
            winner_id
            turns_left
            war_type
            att_id
            def_id
            att_resistance
            def_resistance
            att_points
            def_points
            attacker {
                ...nation_data
            }
            defender {
                ...nation_data
            }
            attacks(min_id: 0) {
                type
                date
            }
        }
    }
}
''' + nation_war_data_fragment
nation_active_wars_query = APIQuery(nation_active_wars_query_text, nation_id=int)

nation_score_query_text = '''
query nation_score_query($nation_id: [Int]) {
    nations(id: $nation_id) {
        data {
            score
        }
    }
}
'''
nation_score_query = APIQuery(nation_score_query_text, nation_id=int)

find_slots_query_text = '''
query find_slots_query($alliance_id: [Int], $min_score: Float, $max_score: Float) {
    nations(alliance_id: $alliance_id, first: 500,
            min_score: $min_score, max_score: $max_score) {
        paginatorInfo {
            hasMorePages
        }
        data {
            id
            vacation_mode_turns
            alliance_position
            beige_turns
            wars {
                att_id
                def_id
                turns_left
            }
        }
    }
}
'''
find_slots_query = APIQuery(find_slots_query_text, True, alliance_id=[int], min_score=float, max_score=float)

spy_sat_query_text = '''
query spy_sat_query($alliance_id: [Int], $min_score: Float, $max_score: Float) {
    nations(alliance_id: $alliance_id, first: 500,
            min_score: $min_score, max_score: $max_score) {
        data {
            id
            spy_satellite
            spies
        }
    }
}
'''
spy_sat_query = APIQuery(spy_sat_query_text, alliance_id=int, min_score=float, max_score=float)

# applications.py

acceptance_query_text = '''
query acceptance_data($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            nation_name
            leader_name
        }
    }
}
'''
acceptance_query = APIQuery(acceptance_query_text, nation_id=int)
