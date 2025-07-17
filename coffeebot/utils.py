import random

from sqlalchemy.sql import text

from coffeebot import config, session
from coffeebot.models import User, Pair


def get_channel(driver, team_name, channel_name):
    """
    Retrieve a channel given a team and channel name.
    Returns the JSON response from the Mattermost API.
    """
    response = driver.channels.get_channel_by_name_and_team_name(
        team_name, channel_name)
    return response


def get_channel_members(driver, team_name, channel_name):
    """
    Retrieve all of the members from a channel given a team and channel name.
    Returns a list of user IDs sorted alphabetically.
    """
    channel = get_channel(driver, team_name, channel_name)
    channel_id = channel['id']

    # By default, the Mattermost API will return only 60 members. Set this to
    # an amount that is at least the number of members in the channel to get
    # all members
    params = {
        'per_page': '10000'
    }
    response = driver.channels.get_channel_members(channel_id, params=params)

    bot = driver.users.get_user('me')
    bot_id = bot['id']

    # Return all of the user IDs excluding the bot's user ID (don't want to
    # count the bot as a user in pairings)
    members = [
        member['user_id'] for member in response if (
            member['user_id'] != bot_id)]

    # Sort the member list alphabetically so that when we create pairs in the
    # database using the list, we won't create duplicate pairs (A <-> B is the
    # same as B <-> A)
    members.sort()

    return members


def create_users(members):
    """
    Create a User object in the database representing each Mattermost user
    given a list of current users in the channel.
    """
    # Set only the users that exist in the input list as active
    session.query(User).update({
        'active': False})
    session.query(User).filter(User.user_id.in_(members)).update({
        'active': True
    }, synchronize_session='fetch')

    for member in members:
        user = session.query(User).filter(User.user_id == member).all()

        if not user:
            user = User(user_id=member, active=True)
            session.add(user)

    session.commit()


def create_pairs(members):
    """
    Create a Pair object in the database representing a potential pairing
    between two Mattermost users given a list of current users in the channel.
    """
    # In order to prevent duplicate pairings (A <-> B is the same as B <-> A),
    # the input list must be alphabetically sorted
    # We iterate over the list of members similar to a selection sort in order
    # create every possible pairing
    for i, first_user in enumerate(members):
        for second_user in members[i + 1:]:
            pair = session.query(Pair).filter(
                Pair.first_user_id == first_user,
                Pair.second_user_id == second_user).all()

            if not pair:
                new_pair = Pair(
                    first_user_id=first_user,
                    second_user_id=second_user,
                    count=0)
                session.add(new_pair)

    session.commit()


def get_pair(members):
    """
    Generate one pair of users from a list of members depending on the
    frequencies of each user's previous pairings.
    """
    member = members[0]

    # Select a single user that is currently active in the channel, has not
    # been paired with another member in this session yet, and has the lowest
    # frequency of previous pairings with the current user
    sql = text("""
        SELECT paired_member
        FROM (
            SELECT p.first_user_id as paired_member, p.count
            FROM pairs p
            JOIN users u ON u.user_id = p.first_user_id
            WHERE p.second_user_id = :member
            AND u.is_paired = 0
            AND u.active = 1
            UNION
            SELECT p.second_user_id as paired_member, p.count
            FROM pairs p
            JOIN users u ON u.user_id = p.second_user_id
            WHERE p.first_user_id = :member
            AND u.is_paired = 0
            AND u.active = 1
        )
        ORDER BY count ASC
        LIMIT 1
    """)

    result = session.execute(sql, {'member': member})
    paired_member = result.first()[0]

    # Increase the historical number of times this pair has been paired up
    # before
    sql = text("""
        UPDATE pairs
        SET count = count + 1
        WHERE (first_user_id = :first_member
            AND second_user_id = :second_member)
        OR (first_user_id = :second_member
            AND second_user_id = :first_member)
    """)

    session.execute(
        sql, {'first_member': member, 'second_member': paired_member})

    # Mark both users as is_paired so that on the next pairing, we won't try to
    # pair either user with a different user
    sql = text("""
        UPDATE users
        SET is_paired = 1
        WHERE user_id = :first_member
        OR user_id = :second_member
    """)

    session.execute(
        sql, {'first_member': member, 'second_member': paired_member})
    session.commit()

    members.remove(member)
    members.remove(paired_member)

    return (member, paired_member)

def _generate_pairs(members, *, alt=False):
    random.shuffle(members)

    pairs = []
    while len(members) > 1:
        pairs.append(get_pair(members))

    # Reset the is_paired flag for each user in preparation for the next time
    # users get paired
    sql = text("""
        UPDATE users
        SET is_paired = 0
    """)

    session.execute(sql)
    session.commit()

    if alt:
        single_person = set(members)-set(pairs)
        return pairs, single_person

    return pairs

def get_pairs_alt(members):
    """ Get pairs with single reminder which gets assigned to any group """
    return _get_pairs(members, alt=True)

def get_pairs(members):
    """ Get only pairs for even number of participating members """
    return _get_pairs(members)


def message_pair(driver, pair):
    """
    Send a group message to both users in a pair notifying them of their
    pairing.
    Returns the JSON response from the Mattermost API.
    """
    user_list = list(pair)

    channel = driver.channels.create_group_message_channel(user_list)
    channel_id = channel['id']

    message = config.MESSAGE
    message_options = {
        "channel_id": channel_id,
        "message": message
    }

    response = driver.posts.create_post(message_options)
    return response


def message_pairs(driver, pairs):
    """
    Send a group message to each pair of users notifying them of their pairing.
    """
    for pair in pairs:
        message_pair(driver, pair)

def get_responsive_members_alt(driver, team_name, channel_name):
    """
    Get responsive members who reacted with thumbs up to the pairing call (not the last message in channel assumed)
    """

    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]

    page = 0
    per_page = 50

    while True:
        resp = driver.posts.get_posts_for_channel(
            channel_id,
            params={"per_page": per_page, "page": page}
        )
        order = resp.get("order", [])
        posts = resp.get("posts", {})

        if not order:
            break

        for post_id in order:
            msg = posts[post_id].get("message", "")
            if "Wanna go" in msg:
                reactions = driver.client.get(f"/posts/{post_id}/reactions")
                return [r["user_id"] for r in reactions if r.get("emoji_name") == "+1"]

        page += 1

    return []


def get_responsive_members(driver, team_name, channel_name):
    """
    Get responsive members who reacted with thumbs up to the pairing call (last message assumed)
    """
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]

    posts = driver.posts.get_posts_for_channel(channel_id, params={"per_page": 1}) # last message only

    recent_post_id = max(posts["posts"], key=lambda post_id: posts["posts"][post_id]["create_at"])
    reactions = driver.client.get(f"/posts/{recent_post_id}/reactions")

    thumbs_up_users = set()
    emoji_name = "+1"
    for reaction in reactions:
        if reaction["emoji_name"] == emoji_name:
            thumbs_up_users.add(reaction["user_id"])

    return list(thumbs_up_users)


def get_user_handles(driver, team_name, channel_name, users):
    """
    Get all user handles from user ids
    """
    return [get_user_handle(driver, team_name, channel_name, user_id) for user_id in users]

def get_user_handle(driver, team_name, channel_name, user_id):
    """
    Get a specific user handle from a user id
    """
    return driver.users.get_user(user_id)["username"]


def message_pairings(driver, team_name, channel_name, pairs):
    """
    One message for each paired partners into the channel
    """
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

def message(driver, team_name, channel_name):
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]
    message = "No participants to pair for today - See you in two weeks."
    driver.posts.create_post({
        "channel_id": channel_id,
        "message": message
        })




def message_pairings_alt(driver, team_name, channel_name, pairs, single):
    """
    One message for each paired partners into the channel
    """
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]
    for index, pair in enumerate(pairs):
        pairA = get_user_handle(driver, team_name, channel_name, pair[0])
        pairB = get_user_handle(driver, team_name, channel_name, pair[1])
        pairC = None
        if single:
            pairC = get_user_handle(driver, team_name, channel_name, list(single)[0])
        message = f"Paired users @{pairA} with @{pairB}"
        if single:
            random_selection = random.randint(0, len(pairs))
            if index == 0: # assign to random group 1
                message = f"Paired users @{pairA} with @{pairB} (User @{pairC} feel free to join them!)"
        
        driver.posts.create_post({
            "channel_id": channel_id,
            "message": message
            })




def send_pairing_call(driver, team_name, channel_name):
    """
    Send call for pairing
    """
    team_id = driver.teams.get_team_by_name(team_name)["id"]
    channel_id = driver.channels.get_channel_by_name(team_id, channel_name)["id"]
    message = f"Wanna go on a coffee / walk- date? React to this message with :+1: then you will be matched"
    driver.posts.create_post({
        "channel_id": channel_id,
        "message": message
        })


