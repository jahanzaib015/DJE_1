import json
import os
from typing import List, Dict, Optional
from ..models.catalog_models import InvestmentOffering, CatalogItem
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class CatalogService:
    """Service for managing investment catalog offerings"""
    
    def __init__(self, catalog_path: Optional[str] = None):
        """
        Initialize catalog service
        
        Args:
            catalog_path: Path to JSON file storing catalog. If None, uses default location.
        """
        if catalog_path is None:
            # Default to data directory in backend
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            catalog_path = os.path.join(backend_dir, "data", "investment_catalog.json")
        
        self.catalog_path = catalog_path
        self._catalog: List[InvestmentOffering] = []
        self._load_catalog()
    
    def _load_catalog(self):
        """Load catalog from JSON file"""
        try:
            os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
            
            if os.path.exists(self.catalog_path):
                with open(self.catalog_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._catalog = [InvestmentOffering(**item) for item in data]
                logger.info(f"✅ Loaded {len(self._catalog)} catalog items from {self.catalog_path}")
            else:
                # Initialize with default catalog if file doesn't exist
                self._initialize_default_catalog()
                logger.info(f"✅ Created default catalog with {len(self._catalog)} items")
        except Exception as e:
            logger.error(f"❌ Failed to load catalog: {e}")
            self._initialize_default_catalog()
    
    def _initialize_default_catalog(self):
        """Initialize with default catalog examples"""
        default_catalog = [
            {
                "id": "precious_metals",
                "label": "Precious metals",
                "synonyms": ["gold", "silver", "platinum", "palladium", "bullion", "commodity metals"],
                "description": "Direct exposure or ETFs tracking precious metals.",
                "constraints": {
                    "instrument_types": ["physical", "etf", "cfds"],
                    "regions": ["EU", "US"],
                    "min_ticket_eur": 10000
                },
                "active": True
            },
            {
                "id": "private_credit",
                "label": "Private Credit",
                "synonyms": ["direct lending", "mezzanine debt", "unitranche", "private debt"],
                "description": "Non-public corporate lending strategies.",
                "constraints": {
                    "instrument_types": ["loan", "fund"],
                    "investor_types": ["professional", "institutional"]
                },
                "active": True
            }
        ]
        self._catalog = [InvestmentOffering(**item) for item in default_catalog]
        self._save_catalog()
    
    def _save_catalog(self):
        """Save catalog to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.catalog_path), exist_ok=True)
            with open(self.catalog_path, 'w', encoding='utf-8') as f:
                data = [item.model_dump() for item in self._catalog]
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"✅ Saved catalog to {self.catalog_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save catalog: {e}")
    
    def get_all_offerings(self, active_only: bool = True) -> List[CatalogItem]:
        """Get all catalog offerings"""
        items = self._catalog
        if active_only:
            items = [item for item in items if item.active]
        return [CatalogItem(**item.model_dump()) for item in items]
    
    def get_offering_by_id(self, offering_id: str) -> Optional[CatalogItem]:
        """Get a specific offering by ID"""
        for item in self._catalog:
            if item.id == offering_id:
                return CatalogItem(**item.model_dump())
        return None
    
    def add_offering(self, offering: InvestmentOffering) -> bool:
        """Add a new offering to the catalog"""
        try:
            # Check if ID already exists
            if any(item.id == offering.id for item in self._catalog):
                logger.warning(f"⚠️ Offering with ID '{offering.id}' already exists")
                return False
            
            self._catalog.append(offering)
            self._save_catalog()
            logger.info(f"✅ Added offering '{offering.id}' to catalog")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add offering: {e}")
            return False
    
    def update_offering(self, offering_id: str, offering: InvestmentOffering) -> bool:
        """Update an existing offering"""
        try:
            for i, item in enumerate(self._catalog):
                if item.id == offering_id:
                    # Preserve ID
                    offering.id = offering_id
                    self._catalog[i] = offering
                    self._save_catalog()
                    logger.info(f"✅ Updated offering '{offering_id}'")
                    return True
            logger.warning(f"⚠️ Offering with ID '{offering_id}' not found")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to update offering: {e}")
            return False
    
    def delete_offering(self, offering_id: str) -> bool:
        """Delete an offering from the catalog"""
        try:
            original_count = len(self._catalog)
            self._catalog = [item for item in self._catalog if item.id != offering_id]
            if len(self._catalog) < original_count:
                self._save_catalog()
                logger.info(f"✅ Deleted offering '{offering_id}'")
                return True
            logger.warning(f"⚠️ Offering with ID '{offering_id}' not found")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to delete offering: {e}")
            return False
    
    def get_catalog_for_indexing(self) -> List[Dict]:
        """Get catalog in format suitable for embedding index"""
        result = []
        for item in self._catalog:
            if not item.active:
                continue
            
            # Combine label, description, and synonyms into searchable text
            texts = [item.label, item.description] + item.synonyms
            if item.constraints.regulatory_tags:
                texts.extend(item.constraints.regulatory_tags)
            
            result.append({
                "id": item.id,
                "texts": texts,
                "item": item
            })
        return result

