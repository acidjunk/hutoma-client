import sys

try:
    user_key = sys.argv[1]
except IndexError:
    user_key = raw_input('User key: ')

print('Fetching AI list for user_key: {0}'.format(user_key))