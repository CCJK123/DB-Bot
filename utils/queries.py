# finance.py

nation_query = '''
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

# bank.py

bank_transactions_query = '''
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

nation_name_query = '''
query nation_name($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            nation_name
        }
    }
}
'''

bank_info_query = '''
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

alliance_name_query = '''
query alliance_name($alliance_id: [Int]) {
    alliances(id: $alliance_id, first: 1) {
        data {
            name
        }
    }
}
'''

# util.py

nation_alliance_query = '''
query nation_info($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            alliance_id
        }
    }
}
'''

alliance_member_res_query = '''
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

alliance_activity_query = '''
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

# war_detector.py

alliance_wars_query = '''
query alliance_wars($alliance_id: [ID]) {
    wars(alliance_id: $alliance_id, days_ago: 6) {
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
'''

individual_war_query = '''
query individual_war($war_id: [Int]) {
    wars(id: $war_id, days_ago: 0, active: false) {
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
'''

# applications.py

acceptance_query = '''
query acceptance_data($nation_id: [Int]) {
    nations(id: $nation_id, first: 1) {
        data {
            nation_name
            leader_name
        }
    }
}
'''