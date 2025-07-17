from mattermostdriver import Driver

from coffeebot import config, utils

import argparse


def get_responsive_members(driver, team_name, channel_name):
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]

    # last message only
    posts = driver.posts.get_posts_for_channel(channel_id, params={"per_page": 1})

    recent_post_id = max(posts["posts"], key=lambda post_id: posts["posts"][post_id]["create_at"])

    reactions = driver.client.get(f"/posts/{recent_post_id}/reactions")

    thumbs_up_users = set()
    for reaction in reactions:
        if reaction["emoji_name"] == "+1":
            thumbs_up_users.add(reaction["user_id"])

    return list(thumbs_up_users)


def get_user_handles(driver, team_name, channel_name, users):
    return [driver.users.get_user(user_id)["username"] for user_id in users]

def get_user_handle(driver, team_name, channel_name, user_id):
    return driver.users.get_user(user_id)["username"]


def message_pairings(driver, team_name, channel_name, pairs):
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]
    for pair in pairs:
        pairA = get_user_handle(driver, team_name, channel_name, pair[0])
        pairB = get_user_handle(driver, team_name, channel_name, pair[1])
        message = f"Paired users @{pairA} with @{pairB}"
        driver.posts.create_post({
            "channel_id": channel_id,
            "message": message
            })


def send_pairing_call(driver, team_name, channel_name):
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]
    message = f"Wanna go on a coffee / walk- date? React to this message with :+1: then you will be matched"
    driver.posts.create_post({
        "channel_id": channel_id,
        "message": message
        })


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
