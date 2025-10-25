## Environment setup (Python 3.10+ recommended)
- Clone repo
- Open VSCode and go to the program folder
- Create a venv `python -m venv .venv`
- Enter the venv `.\.venv\Scripts\activate`
- Run `pip install -r requirements.txt`

## Lichess connection
- Create an account on [Lichess.org](https://lichess.org/signup?referrer=https%3A%2F%2Flichess.org%2F)
- Hover over your name in top right, then select `Preferences`->`API access tokens`->`Click the blue button top right to create a token, give your token a name (ex: lichess-bot-token), select all the permissions then click Create.
- Save this token to the config.yml under the token key. **Note to set all the option values of the bot to Green to ensure maximum compatibility. Remember to save your token and do NOT share it or hardcode it in your code.**

![lichess_pic_2](https://github.com/user-attachments/assets/03492f8e-0ae9-495d-9058-f14cc835c82a)
![lichess_pic_3](https://github.com/user-attachments/assets/db262216-1559-4bbc-ac5e-39b83699bda6)

You can run a quick smoke test in a sample python file as in:

From the command line:

```bash
export lichess_token="YOUR_TOKEN"
```
(in Linux/macOS)

```powershell
set lichess_token="YOUR_TOKEN"
```
(in Windows)

In a test_token.py file run:
```
TOKEN = os.environ["lichess_token"]
H = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/x-ndjson",
}

# Smoke Test for
def smoke_test_token():
    global TOKEN
    H = {"Authorization": f"Bearer {TOKEN}"}
    me = requests.get("https://lichess.org/api/account", headers=H).json()
    print("Logged in as:", me["username"])

smoke_test_token()
```

## Upgrade to bot account
After entering your token in the config.yml file, you can run the following command to upgrade your account to a bot account:
```bash
python lichess_bot.py -u
```

If successful, this command will also start running your bot on lichess. Navigate to lichess.org. You should see a robot icon at the top left corner indicating that you are logged in as a bot. Press play against computer and run your bot in a test game, ensuring it is able to make moves. Your starting bot is a random move bot, so don't expect it to play well!

## Customize your bot
Afterwards see the homemade.py file for sample chess engine classes. A template class called MyBot is provided for you to customize your own bot logic. Expand on the search method to implement your own chess engine logic. You may add any functions you need to the class.

The only file you should change is homemade.py. The other files are driver code that connects to lichess and handles all the API calls. The homemade.py file contains the bot class that you can customize.

## Run your bot for testing
To run your bot, simply execute the following command:
```bash
python lichess_bot.py
```

Or 

```bash
python lichess_bot.py -v
```

If you want to see verbose logging output.

## Running your bot during the tournament

During tournament time we will be using the lichess GUI to send match challenges.

## Algorithms You Should Check Out
### Minimax Search
### Alpha-Beta Pruning
### Iterative Deepening
### Transposition Tables

## Recommended watching
- Great video on chess engine development that covers some of the above algorithms in detail: https://www.youtube.com/watch?v=U4ogK0MIzqk&t=1008s (Note you can skip the parts that cover board representation and move generation since those are already implemented for you in this starter code).

## Citation
If this software has been used for research purposes, please cite it using the "Cite this repository" menu on the right sidebar. For more information, check the [CITATION file](https://github.com/lichess-bot-devs/lichess-bot/blob/master/CITATION.cff).
