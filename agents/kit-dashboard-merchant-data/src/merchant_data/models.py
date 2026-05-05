from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# BIN is determined by Chain (acquiring bank group), not per merchant.
# Derived from comparing multiple VAR sheets.
_CHAIN_TO_BIN: dict[str, str] = {
    "081960": "422108",  # FFB Bank / main KIT POS chain
    "261960": "442114",  # e.g. Ali Baba Smoke and Gift Shop
    "051960": "403982",  # e.g. Holy Smokes Smoke Shop
}

# DC is alphabetically between Delaware and Florida — Maverick API uses strict
# alphabetical ordering with DC at position 9, shifting FL+ by +1 vs the naive list.
# Verified: API state 11 = Georgia (Statesboro GA zip 30458), 37 = Oklahoma (Enid OK zip 73703).
_STATE_CODES: dict[int, str] = {
    1: "Alabama", 2: "Alaska", 3: "Arizona", 4: "Arkansas", 5: "California",
    6: "Colorado", 7: "Connecticut", 8: "Delaware", 9: "District of Columbia",
    10: "Florida", 11: "Georgia", 12: "Hawaii", 13: "Idaho", 14: "Illinois",
    15: "Indiana", 16: "Iowa", 17: "Kansas", 18: "Kentucky", 19: "Louisiana",
    20: "Maine", 21: "Maryland", 22: "Massachusetts", 23: "Michigan",
    24: "Minnesota", 25: "Mississippi", 26: "Missouri", 27: "Montana",
    28: "Nebraska", 29: "Nevada", 30: "New Hampshire", 31: "New Jersey",
    32: "New Mexico", 33: "New York", 34: "North Carolina", 35: "North Dakota",
    36: "Ohio", 37: "Oklahoma", 38: "Oregon", 39: "Pennsylvania",
    40: "Rhode Island", 41: "South Carolina", 42: "South Dakota", 43: "Tennessee",
    44: "Texas", 45: "Utah", 46: "Vermont", 47: "Virginia", 48: "Washington",
    49: "West Virginia", 50: "Wisconsin", 51: "Wyoming",
}

# ZIP prefix → expected state name (for address validation)
_ZIP_PREFIX_TO_STATE: dict[str, str] = {
    "0": None,  # handled per prefix below
    "006": "Puerto Rico", "007": "Puerto Rico", "008": "Virgin Islands", "009": "Puerto Rico",
    "010": "Massachusetts", "011": "Massachusetts", "012": "Massachusetts", "013": "Massachusetts", "014": "Massachusetts",
    "015": "Massachusetts", "016": "Massachusetts", "017": "Massachusetts", "018": "Massachusetts", "019": "Massachusetts",
    "020": "Massachusetts", "021": "Massachusetts", "022": "Massachusetts", "023": "Massachusetts", "024": "Massachusetts",
    "025": "Massachusetts", "026": "Massachusetts", "027": "Massachusetts",
    "028": "Rhode Island", "029": "Rhode Island",
    "030": "New Hampshire", "031": "New Hampshire", "032": "New Hampshire", "033": "New Hampshire", "034": "New Hampshire",
    "035": "New Hampshire", "036": "New Hampshire", "037": "New Hampshire", "038": "New Hampshire",
    "039": "Maine", "040": "Maine", "041": "Maine", "042": "Maine", "043": "Maine", "044": "Maine", "045": "Maine", "046": "Maine", "047": "Maine", "048": "Maine", "049": "Maine",
    "050": "Vermont", "051": "Vermont", "052": "Vermont", "053": "Vermont", "054": "Vermont",
    "055": "Massachusetts",
    "056": "Vermont", "057": "Vermont", "058": "Vermont", "059": "Vermont",
    "060": "Connecticut", "061": "Connecticut", "062": "Connecticut", "063": "Connecticut", "064": "Connecticut", "065": "Connecticut", "066": "Connecticut", "067": "Connecticut", "068": "Connecticut", "069": "Connecticut",
    "070": "New Jersey", "071": "New Jersey", "072": "New Jersey", "073": "New Jersey", "074": "New Jersey", "075": "New Jersey", "076": "New Jersey", "077": "New Jersey", "078": "New Jersey", "079": "New Jersey",
    "080": "New Jersey", "081": "New Jersey", "082": "New Jersey", "083": "New Jersey", "084": "New Jersey", "085": "New Jersey", "086": "New Jersey", "087": "New Jersey", "088": "New Jersey", "089": "New Jersey",
    "100": "New York", "101": "New York", "102": "New York", "103": "New York", "104": "New York", "105": "New York", "106": "New York", "107": "New York", "108": "New York", "109": "New York",
    "110": "New York", "111": "New York", "112": "New York", "113": "New York", "114": "New York", "115": "New York", "116": "New York", "117": "New York", "118": "New York", "119": "New York",
    "120": "New York", "121": "New York", "122": "New York", "123": "New York", "124": "New York", "125": "New York", "126": "New York", "127": "New York", "128": "New York", "129": "New York",
    "130": "New York", "131": "New York", "132": "New York", "133": "New York", "134": "New York", "135": "New York", "136": "New York", "137": "New York", "138": "New York", "139": "New York",
    "140": "New York", "141": "New York", "142": "New York", "143": "New York", "144": "New York", "145": "New York", "146": "New York", "147": "New York", "148": "New York", "149": "New York",
    "150": "Pennsylvania", "151": "Pennsylvania", "152": "Pennsylvania", "153": "Pennsylvania", "154": "Pennsylvania", "155": "Pennsylvania", "156": "Pennsylvania", "157": "Pennsylvania", "158": "Pennsylvania", "159": "Pennsylvania",
    "160": "Pennsylvania", "161": "Pennsylvania", "162": "Pennsylvania", "163": "Pennsylvania", "164": "Pennsylvania", "165": "Pennsylvania", "166": "Pennsylvania", "167": "Pennsylvania", "168": "Pennsylvania", "169": "Pennsylvania",
    "170": "Pennsylvania", "171": "Pennsylvania", "172": "Pennsylvania", "173": "Pennsylvania", "174": "Pennsylvania", "175": "Pennsylvania", "176": "Pennsylvania", "177": "Pennsylvania", "178": "Pennsylvania", "179": "Pennsylvania",
    "180": "Pennsylvania", "181": "Pennsylvania", "182": "Pennsylvania", "183": "Pennsylvania", "184": "Pennsylvania", "185": "Pennsylvania", "186": "Pennsylvania", "187": "Pennsylvania", "188": "Pennsylvania", "189": "Pennsylvania",
    "190": "Pennsylvania", "191": "Pennsylvania", "192": "Pennsylvania", "193": "Pennsylvania", "194": "Pennsylvania", "195": "Pennsylvania", "196": "Pennsylvania",
    "197": "Delaware", "198": "Delaware", "199": "Delaware",
    "200": "District of Columbia", "201": "Virginia", "202": "District of Columbia", "203": "District of Columbia", "204": "District of Columbia", "205": "District of Columbia",
    "206": "Maryland", "207": "Maryland", "208": "Maryland", "209": "Maryland", "210": "Maryland", "211": "Maryland", "212": "Maryland", "214": "Maryland", "215": "Maryland", "216": "Maryland", "217": "Maryland", "218": "Maryland", "219": "Maryland",
    "220": "Virginia", "221": "Virginia", "222": "Virginia", "223": "Virginia", "224": "Virginia", "225": "Virginia", "226": "Virginia", "227": "Virginia", "228": "Virginia", "229": "Virginia",
    "230": "Virginia", "231": "Virginia", "232": "Virginia", "233": "Virginia", "234": "Virginia", "235": "Virginia", "236": "Virginia", "237": "Virginia", "238": "Virginia", "239": "Virginia",
    "240": "Virginia", "241": "Virginia", "242": "Virginia", "243": "Virginia", "244": "Virginia", "245": "Virginia", "246": "Virginia",
    "247": "West Virginia", "248": "West Virginia", "249": "West Virginia", "250": "West Virginia", "251": "West Virginia", "252": "West Virginia", "253": "West Virginia", "254": "West Virginia", "255": "West Virginia", "256": "West Virginia", "257": "West Virginia", "258": "West Virginia", "259": "West Virginia",
    "260": "West Virginia", "261": "West Virginia", "262": "West Virginia", "263": "West Virginia", "264": "West Virginia", "265": "West Virginia", "266": "West Virginia", "267": "West Virginia", "268": "West Virginia",
    "270": "North Carolina", "271": "North Carolina", "272": "North Carolina", "273": "North Carolina", "274": "North Carolina", "275": "North Carolina", "276": "North Carolina", "277": "North Carolina", "278": "North Carolina", "279": "North Carolina",
    "280": "North Carolina", "281": "North Carolina", "282": "North Carolina", "283": "North Carolina", "284": "North Carolina", "285": "North Carolina", "286": "North Carolina", "287": "North Carolina", "288": "North Carolina", "289": "North Carolina",
    "290": "South Carolina", "291": "South Carolina", "292": "South Carolina", "293": "South Carolina", "294": "South Carolina", "295": "South Carolina", "296": "South Carolina", "297": "South Carolina", "298": "South Carolina", "299": "South Carolina",
    "300": "Georgia", "301": "Georgia", "302": "Georgia", "303": "Georgia", "304": "Georgia", "305": "Georgia", "306": "Georgia", "307": "Georgia", "308": "Georgia", "309": "Georgia",
    "310": "Georgia", "311": "Georgia", "312": "Georgia", "313": "Georgia", "314": "Georgia", "315": "Georgia", "316": "Georgia", "317": "Georgia", "318": "Georgia", "319": "Georgia",
    "320": "Florida", "321": "Florida", "322": "Florida", "323": "Florida", "324": "Florida", "325": "Florida", "326": "Florida", "327": "Florida", "328": "Florida", "329": "Florida",
    "330": "Florida", "331": "Florida", "332": "Florida", "333": "Florida", "334": "Florida", "335": "Florida", "336": "Florida", "337": "Florida", "338": "Florida",
    "339": "Florida", "340": "Florida", "341": "Florida", "342": "Florida", "344": "Florida", "346": "Florida", "347": "Florida", "349": "Florida",
    "350": "Alabama", "351": "Alabama", "352": "Alabama", "354": "Alabama", "355": "Alabama", "356": "Alabama", "357": "Alabama", "358": "Alabama", "359": "Alabama",
    "360": "Alabama", "361": "Alabama", "362": "Alabama", "363": "Alabama", "364": "Alabama", "365": "Alabama", "366": "Alabama", "367": "Alabama", "368": "Alabama", "369": "Alabama",
    "370": "Tennessee", "371": "Tennessee", "372": "Tennessee", "373": "Tennessee", "374": "Tennessee", "375": "Tennessee", "376": "Tennessee", "377": "Tennessee", "378": "Tennessee", "379": "Tennessee",
    "380": "Tennessee", "381": "Tennessee", "382": "Tennessee", "383": "Tennessee", "384": "Tennessee", "385": "Tennessee",
    "386": "Mississippi", "387": "Mississippi", "388": "Mississippi", "389": "Mississippi", "390": "Mississippi", "391": "Mississippi", "392": "Mississippi", "393": "Mississippi", "394": "Mississippi", "395": "Mississippi", "396": "Mississippi", "397": "Mississippi",
    "398": "Georgia", "399": "Georgia",
    "400": "Kentucky", "401": "Kentucky", "402": "Kentucky", "403": "Kentucky", "404": "Kentucky", "405": "Kentucky", "406": "Kentucky", "407": "Kentucky", "408": "Kentucky", "409": "Kentucky",
    "410": "Kentucky", "411": "Kentucky", "412": "Kentucky", "413": "Kentucky", "414": "Kentucky", "415": "Kentucky", "416": "Kentucky", "417": "Kentucky", "418": "Kentucky",
    "420": "Kentucky", "421": "Kentucky", "422": "Kentucky", "423": "Kentucky", "424": "Kentucky", "425": "Kentucky", "426": "Kentucky", "427": "Kentucky",
    "430": "Ohio", "431": "Ohio", "432": "Ohio", "433": "Ohio", "434": "Ohio", "435": "Ohio", "436": "Ohio", "437": "Ohio", "438": "Ohio", "439": "Ohio",
    "440": "Ohio", "441": "Ohio", "442": "Ohio", "443": "Ohio", "444": "Ohio", "445": "Ohio", "446": "Ohio", "447": "Ohio", "448": "Ohio", "449": "Ohio",
    "450": "Ohio", "451": "Ohio", "452": "Ohio", "453": "Ohio", "454": "Ohio", "455": "Ohio", "456": "Ohio", "457": "Ohio", "458": "Ohio",
    "460": "Indiana", "461": "Indiana", "462": "Indiana", "463": "Indiana", "464": "Indiana", "465": "Indiana", "466": "Indiana", "467": "Indiana", "468": "Indiana", "469": "Indiana",
    "470": "Indiana", "471": "Indiana", "472": "Indiana", "473": "Indiana", "474": "Indiana", "475": "Indiana", "476": "Indiana", "477": "Indiana", "478": "Indiana", "479": "Indiana",
    "480": "Michigan", "481": "Michigan", "482": "Michigan", "483": "Michigan", "484": "Michigan", "485": "Michigan", "486": "Michigan", "487": "Michigan", "488": "Michigan", "489": "Michigan",
    "490": "Michigan", "491": "Michigan", "492": "Michigan", "493": "Michigan", "494": "Michigan", "495": "Michigan", "496": "Michigan", "497": "Michigan", "498": "Michigan", "499": "Michigan",
    "500": "Iowa", "501": "Iowa", "502": "Iowa", "503": "Iowa", "504": "Iowa", "505": "Iowa", "506": "Iowa", "507": "Iowa", "508": "Iowa", "509": "Iowa",
    "510": "Iowa", "511": "Iowa", "512": "Iowa", "513": "Iowa", "514": "Iowa", "515": "Iowa", "516": "Iowa", "520": "Iowa", "521": "Iowa", "522": "Iowa", "523": "Iowa", "524": "Iowa", "525": "Iowa", "526": "Iowa", "527": "Iowa", "528": "Iowa",
    "530": "Wisconsin", "531": "Wisconsin", "532": "Wisconsin", "534": "Wisconsin", "535": "Wisconsin", "537": "Wisconsin", "538": "Wisconsin", "539": "Wisconsin",
    "540": "Wisconsin", "541": "Wisconsin", "542": "Wisconsin", "543": "Wisconsin", "544": "Wisconsin", "545": "Wisconsin", "546": "Wisconsin", "547": "Wisconsin", "548": "Wisconsin", "549": "Wisconsin",
    "550": "Minnesota", "551": "Minnesota", "553": "Minnesota", "554": "Minnesota", "555": "Minnesota", "556": "Minnesota", "557": "Minnesota", "558": "Minnesota", "559": "Minnesota",
    "560": "Minnesota", "561": "Minnesota", "562": "Minnesota", "563": "Minnesota", "564": "Minnesota", "565": "Minnesota", "566": "Minnesota", "567": "Minnesota",
    "570": "South Dakota", "571": "South Dakota", "572": "South Dakota", "573": "South Dakota", "574": "South Dakota", "575": "South Dakota", "576": "South Dakota", "577": "South Dakota",
    "580": "North Dakota", "581": "North Dakota", "582": "North Dakota", "583": "North Dakota", "584": "North Dakota", "585": "North Dakota", "586": "North Dakota", "587": "North Dakota", "588": "North Dakota",
    "590": "Montana", "591": "Montana", "592": "Montana", "593": "Montana", "594": "Montana", "595": "Montana", "596": "Montana", "597": "Montana", "598": "Montana", "599": "Montana",
    "600": "Illinois", "601": "Illinois", "602": "Illinois", "603": "Illinois", "604": "Illinois", "605": "Illinois", "606": "Illinois", "607": "Illinois", "608": "Illinois", "609": "Illinois",
    "610": "Illinois", "611": "Illinois", "612": "Illinois", "613": "Illinois", "614": "Illinois", "615": "Illinois", "616": "Illinois", "617": "Illinois", "618": "Illinois", "619": "Illinois",
    "620": "Illinois", "622": "Illinois", "623": "Illinois", "624": "Illinois", "625": "Illinois", "626": "Illinois", "627": "Illinois", "628": "Illinois", "629": "Illinois",
    "630": "Missouri", "631": "Missouri", "633": "Missouri", "634": "Missouri", "635": "Missouri", "636": "Missouri", "637": "Missouri", "638": "Missouri", "639": "Missouri",
    "640": "Missouri", "641": "Missouri", "644": "Missouri", "645": "Missouri", "646": "Missouri", "647": "Missouri", "648": "Missouri", "649": "Missouri",
    "650": "Missouri", "651": "Missouri", "652": "Missouri", "653": "Missouri", "654": "Missouri", "655": "Missouri", "656": "Missouri", "657": "Missouri", "658": "Missouri",
    "660": "Kansas", "661": "Kansas", "662": "Kansas", "664": "Kansas", "665": "Kansas", "666": "Kansas", "667": "Kansas", "668": "Kansas", "669": "Kansas",
    "670": "Kansas", "671": "Kansas", "672": "Kansas", "673": "Kansas", "674": "Kansas", "675": "Kansas", "676": "Kansas", "677": "Kansas", "678": "Kansas", "679": "Kansas",
    "680": "Nebraska", "681": "Nebraska", "683": "Nebraska", "684": "Nebraska", "685": "Nebraska", "686": "Nebraska", "687": "Nebraska", "688": "Nebraska", "689": "Nebraska",
    "690": "Nebraska", "691": "Nebraska", "692": "Nebraska", "693": "Nebraska",
    "700": "Louisiana", "701": "Louisiana", "703": "Louisiana", "704": "Louisiana", "705": "Louisiana", "706": "Louisiana", "707": "Louisiana", "708": "Louisiana", "710": "Louisiana", "711": "Louisiana", "712": "Louisiana", "713": "Louisiana", "714": "Louisiana",
    "716": "Arkansas", "717": "Arkansas", "718": "Arkansas", "719": "Arkansas", "720": "Arkansas", "721": "Arkansas", "722": "Arkansas", "723": "Arkansas", "724": "Arkansas", "725": "Arkansas", "726": "Arkansas", "727": "Arkansas", "728": "Arkansas", "729": "Arkansas",
    "730": "Oklahoma", "731": "Oklahoma", "733": "Oklahoma", "734": "Oklahoma", "735": "Oklahoma", "736": "Oklahoma", "737": "Oklahoma", "738": "Oklahoma", "739": "Oklahoma",
    "740": "Oklahoma", "741": "Oklahoma", "743": "Oklahoma", "744": "Oklahoma", "745": "Oklahoma", "746": "Oklahoma", "747": "Oklahoma", "748": "Oklahoma", "749": "Oklahoma",
    "750": "Texas", "751": "Texas", "752": "Texas", "753": "Texas", "754": "Texas", "755": "Texas", "756": "Texas", "757": "Texas", "758": "Texas", "759": "Texas",
    "760": "Texas", "761": "Texas", "762": "Texas", "763": "Texas", "764": "Texas", "765": "Texas", "766": "Texas", "767": "Texas", "768": "Texas", "769": "Texas",
    "770": "Texas", "772": "Texas", "773": "Texas", "774": "Texas", "775": "Texas", "776": "Texas", "777": "Texas", "778": "Texas", "779": "Texas",
    "780": "Texas", "781": "Texas", "782": "Texas", "783": "Texas", "784": "Texas", "785": "Texas", "786": "Texas", "787": "Texas", "788": "Texas",
    "789": "Texas", "790": "Texas", "791": "Texas", "792": "Texas", "793": "Texas", "794": "Texas", "795": "Texas", "796": "Texas", "797": "Texas", "798": "Texas", "799": "Texas",
    "800": "Colorado", "801": "Colorado", "802": "Colorado", "803": "Colorado", "804": "Colorado", "805": "Colorado", "806": "Colorado", "807": "Colorado", "808": "Colorado", "809": "Colorado",
    "810": "Colorado", "811": "Colorado", "812": "Colorado", "813": "Colorado", "814": "Colorado", "815": "Colorado", "816": "Colorado",
    "820": "Wyoming", "821": "Wyoming", "822": "Wyoming", "823": "Wyoming", "824": "Wyoming", "825": "Wyoming", "826": "Wyoming", "827": "Wyoming", "828": "Wyoming", "829": "Wyoming", "830": "Wyoming", "831": "Wyoming",
    "832": "Idaho", "833": "Idaho", "834": "Idaho", "835": "Idaho", "836": "Idaho", "837": "Idaho", "838": "Idaho",
    "840": "Utah", "841": "Utah", "842": "Utah", "843": "Utah", "844": "Utah", "845": "Utah", "846": "Utah", "847": "Utah",
    "850": "Arizona", "851": "Arizona", "852": "Arizona", "853": "Arizona", "855": "Arizona", "856": "Arizona", "857": "Arizona", "859": "Arizona", "860": "Arizona", "863": "Arizona", "864": "Arizona", "865": "Arizona",
    "870": "New Mexico", "871": "New Mexico", "872": "New Mexico", "873": "New Mexico", "874": "New Mexico", "875": "New Mexico", "876": "New Mexico", "877": "New Mexico", "878": "New Mexico", "879": "New Mexico",
    "880": "New Mexico", "881": "New Mexico", "882": "New Mexico", "883": "New Mexico", "884": "New Mexico",
    "885": "Texas",
    "890": "Nevada", "891": "Nevada", "893": "Nevada", "894": "Nevada", "895": "Nevada", "896": "Nevada", "897": "Nevada", "898": "Nevada",
    "900": "California", "901": "California", "902": "California", "903": "California", "904": "California", "905": "California", "906": "California", "907": "California", "908": "California", "909": "California",
    "910": "California", "911": "California", "912": "California", "913": "California", "914": "California", "915": "California", "916": "California", "917": "California", "918": "California", "919": "California",
    "920": "California", "921": "California", "922": "California", "923": "California", "924": "California", "925": "California", "926": "California", "927": "California", "928": "California",
    "930": "California", "931": "California", "932": "California", "933": "California", "934": "California", "935": "California", "936": "California", "937": "California", "938": "California", "939": "California",
    "940": "California", "941": "California", "942": "California", "943": "California", "944": "California", "945": "California", "946": "California", "947": "California", "948": "California", "949": "California",
    "950": "California", "951": "California", "952": "California", "953": "California", "954": "California", "955": "California", "956": "California", "957": "California", "958": "California", "959": "California",
    "960": "California", "961": "California",
    "967": "Hawaii", "968": "Hawaii",
    "970": "Oregon", "971": "Oregon", "972": "Oregon", "973": "Oregon", "974": "Oregon", "975": "Oregon", "976": "Oregon", "977": "Oregon", "978": "Oregon", "979": "Oregon",
    "980": "Washington", "981": "Washington", "982": "Washington", "983": "Washington", "984": "Washington", "985": "Washington", "986": "Washington", "988": "Washington", "989": "Washington",
    "990": "Washington", "991": "Washington", "992": "Washington", "993": "Washington", "994": "Washington",
    "995": "Alaska", "996": "Alaska", "997": "Alaska", "998": "Alaska", "999": "Alaska",
}


def validate_state_from_zip(zip_code: str, state_name: str) -> str | None:
    """Check if zip code matches the state name. Returns warning string or None if OK."""
    if not zip_code or not state_name:
        return None
    prefix3 = zip_code[:3]
    expected = _ZIP_PREFIX_TO_STATE.get(prefix3)
    if expected and expected != state_name:
        return f"⚠️ ZIP {zip_code} → expected {expected}, got {state_name}"
    return None


@dataclass(slots=True)
class VarDownloadResult:
    merchant_name: str
    search_term: str
    profile_url: str
    saved_path: Path

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"Search:     {self.search_term}",
            f"Profile:    {self.profile_url}",
            f"VAR file:   {self.saved_path}",
        ]
        return "\n".join(lines)


@dataclass(slots=True)
class KitCredentials:
    email: str
    password: str
    base_url: str = "https://kitdashboard.com/"
    storage_state: Path = Path("tmp/kit-merchant-state.json")
    verification_code: str | None = None


@dataclass(slots=True)
class VarData:
    """All fields from a TSYS VAR/Download Sheet — assembled from API data only."""
    # Merchant
    legal_name: str
    dba: str
    street: str
    city: str
    state: str
    zip_code: str
    phone: str
    mid: str
    mcc: str
    monthly_volume: float
    # Terminal
    v_number: str
    terminal_number: int       # tid
    store_number: str
    location_number: str
    chain: str
    agent_bank: str
    bin: str                   # derived from chain via _CHAIN_TO_BIN
    # Card types
    accept_visa_mc: bool
    accept_pin_debit: bool
    accept_gift_card: bool
    accept_amex: bool
    accept_discover: bool
    accept_ebt: bool

    def summary(self) -> str:
        def yn(b: bool) -> str: return "Yes" if b else "No"
        return (
            f"Legal Name:    {self.legal_name}\n"
            f"DBA:           {self.dba}\n"
            f"Address:       {self.street}, {self.city}, {self.state} {self.zip_code}\n"
            f"Phone:         {self.phone}\n"
            f"Merchant #:    {self.mid}\n"
            f"V Number:      {self.v_number}\n"
            f"MCC:           {self.mcc}\n"
            f"BIN:           {self.bin}\n"
            f"Chain:         {self.chain}\n"
            f"Agent Bank:    {self.agent_bank}\n"
            f"Terminal #:    {self.terminal_number}\n"
            f"Store #:       {self.store_number}\n"
            f"Location #:    {self.location_number}\n"
            f"Monthly Vol:   ${self.monthly_volume:,.2f}\n"
            f"Visa/MC:       {yn(self.accept_visa_mc)}\n"
            f"PIN Debit:     {yn(self.accept_pin_debit)}\n"
            f"Gift Card:     {yn(self.accept_gift_card)}\n"
            f"Amex:          {yn(self.accept_amex)}\n"
            f"Discover:      {yn(self.accept_discover)}\n"
            f"EBT:           {yn(self.accept_ebt)}"
        )

    def to_dict(self) -> dict:
        return {
            "legal_name": self.legal_name,
            "dba": self.dba,
            "street": self.street,
            "city": self.city,
            "state": self.state,
            "zip": self.zip_code,
            "phone": self.phone,
            "mid": self.mid,
            "mcc": self.mcc,
            "monthly_volume": self.monthly_volume,
            "v_number": self.v_number,
            "terminal_number": self.terminal_number,
            "store_number": self.store_number,
            "location_number": self.location_number,
            "chain": self.chain,
            "agent_bank": self.agent_bank,
            "bin": self.bin,
            "accept_visa_mc": self.accept_visa_mc,
            "accept_pin_debit": self.accept_pin_debit,
            "accept_gift_card": self.accept_gift_card,
            "accept_amex": self.accept_amex,
            "accept_discover": self.accept_discover,
            "accept_ebt": self.accept_ebt,
        }


# Reverse map: "California" → 5
_STATE_NAME_TO_ID: dict[str, int] = {v: k for k, v in _STATE_CODES.items()}


@dataclass(slots=True)
class OnboardingAddress:
    street: str
    city: str
    state: str  # full name, e.g. "California"
    zip: str
    country_id: int = 199  # USA


@dataclass(slots=True)
class OnboardingPrincipal:
    first_name: str
    last_name: str
    title: str  # "CEO" by default. Use "LLC Manager" for LLC, "President" if stated. Never use "Owner".
    ssn: str    # "XXX-XX-XXXX"
    dob: str    # "YYYY-MM-DD"
    email: str
    phone: str
    address: OnboardingAddress
    ownership_percentage: int = 100
    dl_number: str | None = None
    dl_expiration: str | None = None  # "YYYY-MM-DD"
    dl_state: str | None = None       # full state name
    nationality_id: int = 199         # USA


@dataclass(slots=True)
class NewMerchantProfile:
    # Business identity
    legal_name: str
    dba_name: str
    entity_type: str        # "LLC", "Corporation", "SoleProprietorship", "Partnership"
    ein: str                # federal tax ID, digits only
    founded_date: str       # "YYYY-MM-DD"
    mcc_id: int             # internal MCC ID (use MerchantOnboardingService.search_mcc())
    service_description: str
    # Addresses
    business_address: OnboardingAddress
    dba_same_as_company: bool = True
    # Contact
    business_phone: str = ""
    business_email: str = ""
    # Principals (at least one required)
    principals: list[OnboardingPrincipal] = field(default_factory=list)
    # Processing volumes
    monthly_volume: float = 50000.0
    avg_transaction: float = 50.0
    max_transaction: float = 500.0
    # Card types
    accept_credit: bool = True
    accept_pin_debit: bool = True
    accept_ebt: bool = False
    accept_amex: bool = True   # AMEX OptBlue is ON by default (KIT POS standard)
    # Business details
    refund_policy: str = "No refund policy"
    already_processing: bool = False
    has_been_terminated: bool = False
    has_bankruptcy: bool = False
    is_seasonal: bool = False
    inventory_on_site: bool = True
    # Banking (for processing account)
    routing_number: str = ""
    account_number: str = ""
    # API campaign (1579 = KIT POS InterCharge Plus)
    campaign_id: int = 1579


@dataclass(slots=True)
class OnboardingResult:
    app_id: int
    status: str
    message: str = ""
    url: str = ""
    validation_errors: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Application ID: {self.app_id}",
            f"Status:         {self.status}",
        ]
        if self.message:
            lines.append(f"Message:        {self.message}")
        if self.url:
            lines.append(f"URL:            {self.url}")
        if self.validation_errors:
            lines.append("Validation errors:")
            for k, v in self.validation_errors.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id,
            "status": self.status,
            "message": self.message,
            "url": self.url,
            "validation_errors": self.validation_errors,
        }


@dataclass(slots=True)
class MerchantResult:
    merchant_id: str
    merchant_name: str
    profile_url: str
    principal_name: str
    phone: str
    email: str
    business_address: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Merchant:   {self.merchant_name}",
            f"ID:         {self.merchant_id}",
            f"Principal:  {self.principal_name or '(not found)'}",
            f"Phone:      {self.phone or '(not found)'}",
            f"Email:      {self.email or '(not found)'}",
            f"Address:    {self.business_address or '(not found)'}",
            f"Profile:    {self.profile_url}",
        ]
        return "\n".join(lines)
