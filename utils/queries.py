from pnwutils.api import APIQuery

# finance.py

nation_query_text = '''
query nation_info($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            # Display Request, Withdrawal Link
            nation_name

            # Alliance Check
            alliance_id

            # City Grants, Project Grants & War Aid
            num_cities

            # City Grants & Project Grants 
            city_planning
            adv_city_planning

            # Project Grants
            cia
            propb

            # Project Grants & War Aid
            cfce

            # War Aid
            soldiers
            tanks
            aircraft
            ships
            beigeturns
            offensive_wars {
                turnsleft
            }
            defensive_wars {
                turnsleft
            }
            cities {
                barracks
                factory
                airforcebase
                drydock
                name
                infrastructure
            }
            adv_engineering_corps
        }
    }
}
'''
nation_query = APIQuery(nation_query_text, nation_id=int)

# bank.py

bank_transactions_query_text = '''
query bank_transactions($alliance_id: [Int]) {
    alliances(id: $alliance_id, first: 1) {
        data {
            bankrecs {
                sid
                stype
                rid
                rtype
                date
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
}
'''
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
nation_register_query = APIQuery(nation_register_query_text, True, nation_id=int)

alliance_member_res_query_text = '''
query alliance_members_res($alliance_id: [Int], $page: Int) {
    nations(alliance_id: $alliance_id, first: 500, page: $page, vmode: false) {
        paginatorInfo {
            hasMorePages
        }
        data {
            alliance_position
            nation_name
            vmode
            id
            food
            uranium
            cities {
                nuclearpower
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

alliance_tiers_query_text = '''
query nation_discord($alliance_ids: [Int]) {
    alliances(id: $alliance_ids) {
        data {
            nations {
                num_cities
            }
            name
        }
    }
}
'''
alliance_tiers_query = APIQuery(alliance_tiers_query_text, alliance_ids=[int])

# war_detector.py

alliance_wars_query_text = '''
query alliance_wars($alliance_id: [Int]) {
    wars(alliance_id: $alliance_id, first: 1000) {
        data {
            id
            turnsleft
            attid
            defid
            att_alliance_id
            def_alliance_id
            att_resistance
            def_resistance
            attpoints
            defpoints
            attacker {
                nation_name
                score
                num_cities
                warpolicy
                soldiers
                tanks
                aircraft
                ships
                missiles
                nukes
                alliance_position
                alliance {
                    name
                }
            }
            defender {
                nation_name
                score
                num_cities
                warpolicy
                soldiers
                tanks
                aircraft
                ships
                missiles
                nukes
                alliance_position
                alliance {
                    name
                }
            }
        }
    }
}
'''
alliance_wars_query = APIQuery(alliance_wars_query_text, alliance_id=int)

individual_war_query_text = '''
query individual_war($war_id: [Int]) {
    wars(id: $war_id, active: false) {
        data {
            id
            war_type
            attid
            defid
            att_alliance_id
            def_alliance_id
            att_resistance
            def_resistance
            attpoints
            defpoints
            attacker {
                nation_name
                score
                num_cities
                warpolicy
                soldiers
                tanks
                aircraft
                ships
                missiles
                nukes
                alliance_position
                alliance {
                    name
                }
            }
            defender {
                nation_name
                score
                num_cities
                warpolicy
                soldiers
                tanks
                aircraft
                ships
                missiles
                nukes
                alliance_position
                alliance {
                    name
                }
            }
        }
    }
}
'''
individual_war_query = APIQuery(individual_war_query_text, war_id=int)

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
