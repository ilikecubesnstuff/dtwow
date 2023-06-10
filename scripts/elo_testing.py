from collections import Counter
from tqdm import tqdm

import numpy as np  # not in requirements.txt!


# setup
np.random.seed(0)

class Response:
    counter = 0

    def __init__(self):
        self.n = Response.counter
        Response.counter += 1
        self.rating = 1000

    def __repr__(self):
        return f"Response(id={self.n}, rating={self.rating})"

    def __hash__(self):
        return hash(self.n)
    
    def beats(self, other, factor = 1):
        """
        update ratings of a and b if a.beats(b)
        """
        if isinstance(factor, tuple):
            factor1, factor2 = factor
        else:
            factor1 = factor2 = factor
        rating_difference = self.rating - other.rating
        E_self = 1/(1 + 10**(rating_difference/400))
        self.rating = self.rating + 50 * E_self * factor1
        other.rating = other.rating - 50 * E_self * factor2

class User:

    def __init__(self):
        self.votes = 0
        self.history = []

    def __repr__(self):
        history = ','.join(f'{r1.n}|{r2.n}' for r1, r2 in self.history)
        return f"User(votes={self.votes}, history={history})"


# parameters
R = 50
N = 200
V = 2000

# create R responses and N users
responses = [Response() for _ in range(R)]
users = [User() for _ in range(N)]

# simulate voting period with (maximum) V votes
a = 4
m = N
votes = m * np.random.pareto(a, V) % N  # 80-20 rule, roughly
votes = np.round(votes[votes < N-1])
# i am assuming a Pareto distribution roughly models votes from a fixed set of users.
# this means roughly 80% of votes would come from roughly 20% of voting users.
# at the very least, the pareto distribution is skewed, and the influence of each
# individual voter should be sensible regardless of the distribution being skewed.
# the exercise here is coming up with a weighing of votes that still gives voters a
# desirable and sensible influence over the response ratings (and therefore standings).

for vote in votes:
    user = users[int(vote)]
    user.votes += 1

    c = Counter( sum(user.history, ()) )  # flattened voter history
    c.update( {response: 0 for response in responses} )

    _, lowest = c.most_common()[-1]
    pool = [response for response, freq in c.most_common() if freq == lowest]
    response1 = np.random.choice(pool)
    response2 = np.random.choice([response for response in responses if not any(response in h and response1 in h for h in user.history)])
    # print(user, f'{response1.n}|{response2.n}')

    if np.random.random() < 0.5: response2, response1 = response1, response2
    user.history.append((response1, response2))
print('\n\n\n\nAFTER VOTING PERIOD:')

# print all users
for u in sorted(users, key=lambda u: u.votes):
    print(u)

# calculate response ratings
for user in users:
    c = Counter( sum(user.history, ()) )  # flattened voter history
    
    for r1, r2 in user.history:
        f1 = 1/c[r1]
        f2 = 1/c[r2]
        r1.beats(r2, (f1, f2))
        # r1.beats(r2)

# print all responses
for r in sorted(responses, key=lambda r: r.rating):
    print(r)

