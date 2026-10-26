import sys,asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.mcp.client import discover
from integrations.core import RESULTS,save
async def main():
 await asyncio.gather(*(discover(p) for p in ('tutu','2gis','liteapi','geoapify','openweather_mcp')))
 save('mcp_discovery_results.json',RESULTS)
asyncio.run(main())
