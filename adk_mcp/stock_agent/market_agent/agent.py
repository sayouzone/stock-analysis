from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent

class MarketAgent(BaseAgent):
    """
    An agent that coordinates market analysis tasks using a market analyst LLM agent.
    This agent uses the provided market analyst to perform analyses and generate reports.
    It extends the BaseAgent class from the Google ADK framework.
    """

    # --- Field Declarations for Pydantic ---
    # Declare the agents passed during initialization as class attributes with type hints
    market_analyst: LlmAgent

    # model_config allows setting Pydantic configurations if needed, e.g., arbitrary_types_allowed
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        price_analyst: LlmAgent,
    ):
        """
        Initializes the MarketAgent with the given name and market analyst agent.
        Args:
            name (str): The name of the MarketAgent.
            market_analyst (LlmAgent): An instance of LlmAgent that performs market analysis.
        """
        # Create internal agents *before* calling super().__init__

        # Define the sub_agents list for the framework
        sub_agents_list = [
            price_analyst,
        ]

        # Pydantic will validate and assign them based on the class annotations.
        super().__init__(
            name=name,
            price_analyst=price_analyst,
            sub_agents=sub_agents_list,
        )

