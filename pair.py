from mattermostdriver import Driver

from coffeebot import config, utils

import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", action='store_true')

    args = parser.parse_args()
    pairing_call = not args.pair
    print("Creating Mattermost Driver...")
    driver_options = {
        'url': config.URL,
        'token' : config.PASSWORD,
        #'login_id': config.USERNAME,
       # 'password': config.PASSWORD,
        'port': config.PORT
    }
    driver = Driver(driver_options)

    print("Authenticating...")
    driver.login()
    driver.users.get_user('me')
    print("Successfully authenticated.")

    team_name = config.TEAM_NAME
    channel_name = config.CHANNEL_NAME

    if pairing_call:
        send_pairing_call(driver, team_name, channel_name)
    else:
        print("here")
        import sys
        sys.exit(0)
        members = get_responsive_members(driver, team_name, channel_name)
        print(members)
        print(get_user_handles(driver, team_name, channel_name, members))

        members = utils.get_channel_members(driver, team_name, channel_name)

        print("Preparing participants database...")
        utils.create_users(members)
        utils.create_pairs(members)
        print("Succesfully prepared participants database.")

        print("Pairing Coffee Buddies participants...")
        pairs = utils.get_pairs(members)
        print("Successfully paired Coffee Buddies participants.")
        print(pairs)
        print("Messaging pairing...")
        message_pairings(driver, team_name, channel_name, pairs)
    #

if __name__ == '__main__':
    main()
