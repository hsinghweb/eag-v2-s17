# 📈 Market Briefing

{{#if all_globals_schema.consolidated_apple_price}}
# Apple Stock Price Report

{{#each all_globals_schema.consolidated_apple_price}}
## Current Price ({{this.symbol}})

- **Price:** ${{this.price}} {{this.currency}}
- **Exchange:** {{this.exchange}}
- **Last Updated:** {{this.timestamp}}
{{/each}}
{{else}}
# Apple Stock Price Report

No current stock price data available for Apple.
{{/if}}