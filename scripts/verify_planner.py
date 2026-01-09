
import asyncio
import sys
import os

# Adjust path to include src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents.sub_agents.planner import planner

async def main():
    print("Initializing planner...")
    agent = await planner()
    print(f"Agent initialized: {agent.name}")
    print(f"Model: {agent.model.model}")
    
    # Test connection (simple generation)
    print("Testing connection...")
    try:
        response = await agent.run("Hello, are you connected?")
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
