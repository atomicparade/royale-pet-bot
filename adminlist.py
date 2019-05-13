import os

class AdminList:
    def __init__(self):
        self.list = []

    def authenticate(self, user, password):
        if user in self.list:
            return True

        if password == os.getenv("DISCORD_BOT_ADMIN_PASSWORD"):
            self.list.append(user)
            return True
        else:
            return False

    def is_authorized(self, user):
        return user in self.list
