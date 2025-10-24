Environment Setup:
- Clone repo
- Open VSCode and go to the program folder
- Create a venv `python -m venv .venv`
- Enter the venv `.\.venv\Scripts\activate`
- Run `pip install -r requirements.txt`

Lichess Connection:
- Create an account on [Lichess.org](https://lichess.org/signup?referrer=https%3A%2F%2Flichess.org%2F)
- Hover over your name in top right, then select `Preferences`->`API access tokens`->`Click the blue button top right to create a token, give your token a name (ex: lichess-bot-token), select all the permissions then click `Create`. Save this token to the config.yml under the token key. **Note to set all the option values of the bot to Green to ensure maximum compatibility. Remember to save your token and do NOT share it or hardcode it in your code.**

![lichess_pic_2](https://github.com/user-attachments/assets/03492f8e-0ae9-495d-9058-f14cc835c82a)
![lichess_pic_3](https://github.com/user-attachments/assets/db262216-1559-4bbc-ac5e-39b83699bda6)



You can run a quick smoke test in a sample python file as in:

From the command line:
```export lichess_token = "YOUR_TOKEN"```

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

Afterwards see the homemady.py file for sample chess engine classes, for which you will subclass your own, namely from the MinimalEngine class from the LichessBot/lib/engine_wrapper.py file. 


## Citation
If this software has been used for research purposes, please cite it using the "Cite this repository" menu on the right sidebar. For more information, check the [CITATION file](https://github.com/lichess-bot-devs/lichess-bot/blob/master/CITATION.cff).
