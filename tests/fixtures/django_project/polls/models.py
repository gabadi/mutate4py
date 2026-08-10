"""An app-loaded module (issue 05): django.setup() imports every installed
app's models during framework bootstrap, so this file is already in
sys.modules by the time a Worker primes — it degrades to the subprocess
executor rather than using the warm forking path."""

from django.db import models


class Question(models.Model):
    text = models.CharField(max_length=200)
    votes = models.IntegerField(default=0)

    def is_popular(self):
        return self.votes > 10
