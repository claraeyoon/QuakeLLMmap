from __future__ import annotations
import math
from typing import List, Dict, Any, Tuple

USGS_MMI_DEFINITIONS = [
    {
        "mmi": 1.0,
        "label": "I. Not Felt",
        "description": "Not felt except by a very few under especially favorable conditions."
    },
    {
        "mmi": 2.0,
        "label": "II. Weak",
        "description": "Felt only by a few persons at rest, especially on upper floors of buildings. Delicately suspended objects may swing."
    },
    {
        "mmi": 3.0,
        "label": "III. Slight",
        "description": "Felt quite noticeably by persons indoors, especially on upper floors of buildings. Many people do not recognize it as an earthquake. Standing motor cars may rock slightly. Vibrations similar to the passing of a truck. Duration estimated."
    },
    {
        "mmi": 4.0,
        "label": "IV. Moderate",
        "description": "Felt indoors by many, outdoors by few during the day. At night, some awakened. Dishes, windows, doors disturbed; walls make cracking sound. Sensation like heavy truck striking building. Standing motor cars rocked noticeably."
    },
    {
        "mmi": 5.0,
        "label": "V. Rather Strong",
        "description": "Felt by nearly everyone; many awakened. Some dishes, windows broken. Unstable objects overturned. Pendulum clocks may stop."
    },
    {
        "mmi": 6.0,
        "label": "VI. Strong",
        "description": "Felt by all, many frightened. Some heavy furniture moved; a few instances of fallen plaster. Damage slight. Chimneys damaged."
    },
    {
        "mmi": 7.0,
        "label": "VII. Very Strong",
        "description": "Damage negligible in buildings of good design and construction; slight to moderate in well-built ordinary structures; considerable damage in poorly built or badly designed structures; some chimneys broken."
    },
    {
        "mmi": 8.0,
        "label": "VIII. Destructive",
        "description": "Damage slight in specially designed structures; considerable damage in ordinary substantial buildings with partial collapse. Damage great in poorly built structures. Fall of chimneys, factory stacks, columns, monuments, walls. Heavy furniture overturned."
    },
    {
        "mmi": 9.0,
        "label": "IX. Violent",
        "description": "Damage considerable in specially designed structures; well-designed frame structures thrown out of plumb. Damage great in substantial buildings, with partial or complete collapse. Buildings shifted off foundations. Liquefaction and ground cracking."
    },
    {
        "mmi": 10.0,
        "label": "X. Intense",
        "description": "Some well-built wooden structures destroyed; most masonry and frame structures destroyed with foundations. Rails bent. Landslides considerable from river banks and steep slopes."
    },
    {
        "mmi": 11.0,
        "label": "XI. Extreme",
        "description": "Few, if any, (masonry) structures remain standing. Bridges destroyed. Broad fissures in ground. Underground pipe lines completely out of service. Earth slumps and land slips in soft ground."
    },
    {
        "mmi": 12.0,
        "label": "XII. Cataclysmic",
        "description": "Damage total. Practically all works of construction are damaged greatly or destroyed. Lines of sight and level are distorted. Objects thrown into the air."
    }
]

class LocalMMIKnowledgeBase:
    """
    Embedded vector and semantic knowledge base for USGS MMI I-XII scales.
    Zero cloud requirements; completely local.
    """

    def __init__(self):
        self.entries = USGS_MMI_DEFINITIONS

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieves closest MMI definitions based on keyword matching / term overlap."""
        if not query:
            return self.entries[4:7]  # Default MMI V-VII

        query_terms = set(query.lower().split())

        scored = []
        for item in self.entries:
            text = f"{item['label']} {item['description']}".lower()
            text_terms = set(text.split())
            overlap = len(query_terms.intersection(text_terms))
            scored.append((overlap, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]
