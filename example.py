import sys
from hutoma import HutomaUserKey

try:
    user_key = sys.argv[1]
except IndexError:
    user_key = raw_input('User key: ')

# print('Fetching AI list for user_key: {0}'.format(user_key))
h = HutomaUserKey('sdkjdslk')
temp = h.get_ai_list()
print(temp)
temp = h.get_ai('36f96e07-1dd8-4b71-a77b-a6e0b1bddc48')
print(temp)
