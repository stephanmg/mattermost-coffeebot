import argparse
from mattermostdriver import Driver
from coffeebot import config, utils

def main():
    # Get CLI arguments for crontab, either call for pairing or pair users
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", action='store_true')
    args = parser.parse_args()
    pairing_call = not args.pair

    # Connect to Bot with API token, note that Bot needs to be member of the 
    # team, otherwise the bot would need admin privileges, bot needs to be
    # added to the ~coffee-buddies channel or any other channel you desire
    driver_options = {
        'url': config.URL,
        'token' : config.PASSWORD,
        'port': config.PORT
    }
    driver = Driver(driver_options)
    driver.login()
    driver.users.get_user('me')

    # team name and channel name from .env configuration file
    team_name = config.TEAM_NAME
    channel_name = config.CHANNEL_NAME

    # Either send pairing call ...
    if pairing_call:
        utils.send_pairing_call(driver, team_name, channel_name)
    else:  
        # all members who upvoted with thumbs up
        members = utils.get_responsive_members(driver, team_name, channel_name)

        # create pairings
        utils.create_users(members)
        utils.create_pairs(members)
        pairs = utils.get_pairs(members)

        # finally for each pair a message in the channel
        utils.message_pairings(driver, team_name, channel_name, pairs)

if __name__ == '__main__':
    main()

