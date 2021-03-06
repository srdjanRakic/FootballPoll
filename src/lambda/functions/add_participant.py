import boto3
import time
import datetime
import re
import json
from boto3.dynamodb.conditions import Key
        
dynamodb = boto3.resource('dynamodb')
responseHeaders = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Credentials' : True }

def get_current_poll_id(second_attempt = False):
    """Tries 2 times to access the config table and takes the current poll id.

    Parameters:
        second_attempt: Flag for the second attempt.

    Returns:
        Current poll id.
    """

    config_table = dynamodb.Table('fp.config')

    try:
        response = config_table.get_item(
            Key={
                'id': 'CurrentPoll'
            }
        )
    except Exception:
        if second_attempt:
            raise Exception('Database error!')

        # tries again if the first attempt failed
        time.sleep(1)
        return get_current_poll_id(True)
        
    return int(response['Item']['value'])

def get_item_polls_max(poll_id, second_attempt = False):
    """Tries 2 times to access the polls table and takes the max attribute.

    Parameters:
        poll_id: Current poll id.
        second_attempt: Flag for the second attempt.

    Returns:
        Max attribute from the current poll.
    """

    polls_table = dynamodb.Table('fp.polls')

    try:
        response = polls_table.get_item(
            Key={
                'id': poll_id
            }
        )
    except Exception:
        if second_attempt:
            raise Exception('Database error!')

        # tries again if the first attempt failed
        time.sleep(1)
        return get_item_polls_max(poll_id, True)

    return response['Item']['max']

def query_participants(poll_id, last_evaluated_key = None, second_attempt = False):
    """Query the participants table and returns all results for given poll, if the first attempt failed or has unprocessed keys tries again.

    Parameters:
        last_evaluated_key: Last evaluated key, if some data is not read.
        second_attempt: Flag for the second attempt.

    Returns:
        List with participants.
    """
    
    result = []

    participants_table = dynamodb.Table('fp.participants')

    try:
        if last_evaluated_key:
            response = participants_table.query(
                KeyConditionExpression=Key('poll').eq(poll_id),
                ConsistentRead=True,
                ExclusiveStartKey=last_evaluated_key
            )
        else:
            response = participants_table.query(
                KeyConditionExpression=Key('poll').eq(poll_id),
                ConsistentRead=True
            )
    except Exception:
        if second_attempt:
            raise Exception('Database error!')
        
        # tries again if the first attempt failed
        time.sleep(1)
        return query_participants(poll_id, last_evaluated_key, True)
       
    if 'Items' in response:
        result = response['Items']

    if (not second_attempt) and ('LastEvaluatedKey' in response):
        # tries again if there are unprocessed keys
        try:
            time.sleep(1)
            second_result = query_participants(poll_id, response['LastEvaluatedKey'], True)
        except Exception:
            raise Exception('Database error!')
        
        result.append(second_result)
    
    return result

def put_item_participants(item, second_attempt = False):
    """Tries 2 times to put the participant in the participants table.

    Parameters:
        item: Item with attributes of the participants table (poll, added, person, friend).
        second_attempt: Flag for the second attempt.

    Returns:
        Max attribute from the current poll.
    """

    participants_table = dynamodb.Table('fp.participants')
    
    try:
        participants_table.put_item(
            Item=item
        )
    except Exception:
        if second_attempt:
            raise Exception('Database error!')

        # tries again if the first attempt failed
        time.sleep(1)
        return put_item_participants(item, True)

    return {
        'statusCode': 200,
        'headers': responseHeaders,
        'body': json.dumps({ 'added': item['added'] })
    }

def add_participant(event, context):
    """Adds a participant into the current poll.

    Returns:
        Status of adding.
    """

    if event['body'] is None:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'No request body!'})
        }

    try:
        requestBody = json.loads(event['body'])
    except:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Bad request body!'})
        }
    
    if type(requestBody) != dict:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Bad request body!'})
        }
    
    if 'person' not in requestBody:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'person parameter doesn\'t exist in the API call!'})
        }
    
    # lower letters and remove all unnecessary whitespaces
    person = ' '.join(requestBody['person'].lower().split())
    friend = '/'

    if 'friend' in requestBody:
        friend = ' '.join(requestBody['friend'].lower().split())

    if len(person) < 3:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Person name should contains at least 3 letters!'})
        }

    if len(person) > 25:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Too long person name!'})
        }
    
    if len(friend) == 0:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Friend name should contains at least 1 letter!'})
        }

    if len(friend) > 25:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Too long friend name!'})
        }

    # person allowed characters - lower letters (mac cyrilic, eng latin), digits, whitespace between characters
    mac_alphabet = 'абвгдѓежзѕијклљмнњопрстќуфхцчџш'
    search_not_allowed = '[^a-z0-9 ' + mac_alphabet + ' ]'

    if re.search(search_not_allowed, person):
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'person value contains not allowed characters!'})
        }

    # friend allowed characters - lower letters (mac cyrilic, eng latin), digits, +, whitespace between characters
    search_not_allowed = search_not_allowed[:-1] + '+]'
    
    if (friend != '/') and re.search(search_not_allowed, friend):
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'friend value contains not allowed characters!'})
        }

    # get current poll id
    try:
        current_poll_id = get_current_poll_id()
    except Exception:
        return {
            'statusCode': 500,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Database error!'})
        }

    # get max participants
    polls_table = dynamodb.Table('fp.polls')

    try:
        current_poll = polls_table.get_item(
            Key={
                'id': current_poll_id
            }
        )
    except Exception:
        return {
            'statusCode': 500,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Database error!'})
        }

    max_participants = current_poll['Item']['max']

    # query participants
    try:
        participants = query_participants(current_poll_id)
    except Exception:
        return {
            'statusCode': 500,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Database error!'})
        }

    if len(participants) == max_participants:
        return {
            'statusCode': 400,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'No more participants in this poll!'})
        }

    # check for duplicate
    if friend == '/':
        for participant in participants:
            if (participant['person'] == person) and (participant['friend'] == '/'):
                return {
                    'statusCode': 400,
                    'headers': responseHeaders,
                    'body': json.dumps({'errorMessage': 'Participant ' + person + ' exists in the current poll!'})
                }

    # add the participant
    added = int(datetime.datetime.now().timestamp() * 1000)

    try:
        put_status = put_item_participants({
            'poll': current_poll_id,
            'added': added,
            'person': person,
            'friend': friend
        })
    except Exception:
        return {
            'statusCode': 500,
            'headers': responseHeaders,
            'body': json.dumps({'errorMessage': 'Database error!'})
        }

    return put_status