import configparser
from langchain_groq import ChatGroq
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType

# Load config
config = configparser.ConfigParser()
config.read("config.ini")
GROQ_API_KEY = config["groq"]["api_key"]

def calculator(operation: str) -> str:
    try:
        return str(eval(operation))
    except Exception as e:
        return f"Error: {e}"

calc_tool = Tool(
    name="Calculator",
    func=calculator,
    description="Solve math expressions"
)

llm = ChatGroq(
    model="llama3-70b-8192",
    temperature=0,
    api_key=GROQ_API_KEY
)

agent = initialize_agent(
    tools=[calc_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

response = agent.run("What is 87*45?")
print(response)
