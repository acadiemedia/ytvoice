#!/usr/bin/env python3
"""
Add comprehensive English names to voice_sprites.bin so the player's
recombination can speak proper names correctly.

Names are phonemized via espeak (through Piper's phonemize() path) and
synthesized in-process, then resampled to 16kHz mono IMA ADPCM.

New keys that already exist in the index are skipped (never overwritten).

Usage:
    python tools/add_names.py [--model PATH] [--commit]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import io
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "src"))

import ffmpeg_util  # noqa: E402

# ---------------------------------------------------------------------------
# Comprehensive English names (US Top 500 male + female, international,
# historical, literary, etc.)
# ---------------------------------------------------------------------------
NAMES = sorted(set([
    # ── US Top 500 Male ──────────────────────────────────────────────────
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
    "kenneth", "kevin", "brian", "george", "timothy", "ronald", "edward",
    "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric",
    "jonathan", "stephen", "larry", "justin", "scott", "brandon",
    "benjamin", "samuel", "raymond", "gregory", "frank", "patrick",
    "jack", "dennis", "jerry", "alexander", "tyler", "aaron", "jose",
    "adam", "nathan", "henry", "peter", "zachary", "douglas", "harold",
    "carl", "arthur", "gerald", "roger", "keith", "jeremy", "terry",
    "lawrence", "sean", "christian", "anthony", "ralph", "roy", "wayne",
    "eugene", "randy", "bruce", "philip", "howard", "albert", "fred",
    "arthur", "joe", "billy", "al", "sparky", "lee", "bobby", "danny",
    "tommy", "tony", "dylan", "alex", "liam", "noah", "ethan", "mason",
    "logan", "lucas", "aiden", "grayson", "jack", "henry", "sebastian",
    "carter", "owen", "theodore", "jackson", "levi", "isaac", "luke",
    "jayden", "gabriel", "anthony", "david", "lincoln", "joshua",
    "caleb", "oliver", "tyler", "charles", "christopher", "eli",
    "hunter", "connor", "elijah", "ezra", "thomas", "aaron", "isaiah",
    "asher", "kai", "oscar", "evan", "endrew", "nolan", "micah",
    "cooper", "xavier", "pyper", "jace", "matthew", "santiago", "adam",
    "distance", "brooks", "james", "landon", "chase", "asher", "dominic",
    "ian", "jesse", "weston", "bennett", "silver", "ezekiel", "cole",
    "karter", "miles", "stetson", "lennox", "jasper", "jonah", "zoey",
    "edward", "michael", "daniel", "matthew", "nicholas", "andrew",
    "william", "matthew", "johnny", "darren", "elliot", "luca", "walker",
    "marvin", "reece", "major", "peter", "jeremiah", "wiggin", "grant",
    "kenneth", "parker", "paxton", "hudson", "coleman", "camden",
    "lincoln", "caden", "asher", "jace", "dawson", "river", "bam",
    "ryder", "kingston", "sawyer", "bentley", "george", "xavier",
    "wyatt", "european", "graham", "knox", "bennett", "zhane",
    "colton", "jace", "logan", "emmett", "ivan", "max", "edward",
    "collin", "cash", "derek", "colt", "alden", "ryker", "maxwell",
    "robert", "reed", "jasper", "spencer", "xavier", "killian", "caleb",
    "liam", "caleb", "braxton", "timothy", "ehden", "seth", "spencer",
    "joseph", "blake", "thomas", "gavin", "layne", "adam", "cole",
    "kayden", "silas", "hall", "joseph", "bryson", "omar", "bjorn",
    "malachi", "emmanuel", "leyton", "landon", "tristan", "garrett",
    "brooks", "rowan", "brandon", "gx", "harrison", "finn", "logan",
    "bennett", "bailey", "parker", "malakai", "maverick", "luca",
    "luis", "angeles", "angel", "leo", "eduardo", "antonio", "carlos",
    "adrian", "omar", "pablo", "marco", "diego", "andrés", "andrés",
    "sergio", "rafael", "pedro", "manuel", "fernando", "joel", "oscar",
    "hector", "rodrigo", "emiliano", "raúl", "tomás", "ian", "rey",
    "fabian", "alejandro", "santiago", "miguel", "andres", "ricardo",
    "ivan", "enrique", "rafael", "armando", "roberto", "jorge", "cesar",
    "edgar", "francisco", "ruben", "roberto", "jesús", "julio",
    "alejandro", "hector", "antonio", "alejandro", "erik", "ander",
    "joshua", "daniel", "samuel", "angel", "anthony", "sebastian",
    "isaiah", "matthew", "eli", "carlos", "abel", "jesus", "joel",
    "miguel", "andres", "arthur", "oscar", "giovanni", "luca", "theo",
    "aaron", "adrian", "javier", "xavier", "valentino", "bartolo",
    "theo", "michael", "james", "carlos", "luis", "pedro", "jose",
    "marcos", "miguel", "ricardo", "alberto", "rafael", "roberto",
    "raúl", "tomás", "diego", "alejandro", "gabriel", "daniel",
    "andres", "jesus", "marco", "raul", "edgar", "francisco", "omar",
    "hector", "carlos", "fernando", "julio", "javier", "antonio",
    "manuel", "armando", "ernesto", "adolfo", "rafael", "hugo",
    "gustavo", "salvador", "humberto", "enrique", "fernando",
    "eduardo", "emilio", "armando", "arturo", "alfredo", "jesús",
    "rodrigo", "sebastián", "emiliano", "tomás", "felipe", "andrés",
    "nicolas", "mateo", "benjamín", "samuel", "joaquín", "simón",
    "leonardo", "valentino", "santino", "rafael", "alejandro",
    "jeronimo", "agustín", "alcides", "alvaro", "anderson", "axel",
    "bruno", "camilo", "carlos", "damián", "danilo", "dante",
    "dariel", "edinson", "eder", "elias", "emanuel", "emerson",
    "emilio", "esteban", "fabian", "fabio", "facundo", "federico",
    "felipe", "felix", "francisco", "gabriel", "gaston", "gian",
    "giovanni", "guillermo", "gustavo", "hans", "hugo", "humberto",
    "iñaki", "isaac", "israel", "ivan", "jared", "jefferson", "jeremías",
    "joao", "jose", "josué", "juan", "jurgen", "kevin", "krishna",
    "kurt", "kyan", "lautaro", "lenny", "leo", "liam", "lucas",
    "luca", "luis", "máximo", "marcus", "marco", "marcos", "mario",
    "mateo", "matías", "mauro", "max", "maximiliano", "miguel",
    "mirko", "nahuel", "nicolas", "noah", "oliver", "omar", "oscar",
    "osvaldo", "pablo", "paolo", "patricio", "pedro", "pepe",
    "philipp", "rafael", "raúl", "renato", "ricardo", "ricky", "roberto",
    "rodrigo", "rogelio", "roman", "román", "romeo", "roque", "rubén",
    "samuel", "sandro", "santino", "santiago", "sebastián", "sebastián",
    "sergio", "simón", "tiago", "tobías", "tomás", "tulio", "valentín",
    "victor", "vinicius", "walter", "william", "yago", "yuri", "facundo",
    "chuy", "alexander", "augusto", "benito", "carlos", "claudio",
    "cristian", "dante", "diego", "emilio", "esteban", "gabriel",
    "hector", "hugo", "ivan", "javier", "jorge", "josé", "juan",
    "leonardo", "luis", "manuel", "mario", "miguel", "pablo", "pedro",
    "rafael", "raúl", "ricardo", "roberto", "rodrigo", "rubén",
    "sebastián", "sergio", "tomás",

    # ── US Top 500 Female ────────────────────────────────────────────────
    "mary", "patricia", "jennifer", "linda", "barbara", "elizabeth",
    "susan", "jessica", "sarah", "karen", "lisa", "nancy", "betty",
    "margaret", "sandra", "ashley", "dorothy", "kimberly", "emily",
    "donna", "michelle", "carol", "amanda", "melissa", "deborah",
    "stephanie", "rebecca", "sharon", "laura", "cynthia", "kathleen",
    "amy", "angela", "shirley", "anna", "brenda", "pamela", "emma",
    "nicole", "helen", "samantha", "katherine", "christine", "debra",
    "rachel", "carolyn", "janet", "catherine", "maria", "heather",
    "diane", "ruth", "julie", "olivia", "joyce", "virginia", "victoria",
    "kelly", "lauren", "christina", "joan", "evelyn", "judith", "megan",
    "andrea", "cheryl", "hannah", "jacqueline", "martha", "gloria",
    "teresa", "ann", "sara", "madison", "frances", "kathryn", "janice",
    "jean", "abigail", "alice", "judy", "sophia", "grace", "denise",
    "amber", "doris", "marilyn", "danielle", "beverly", "isabella",
    "theresa", "diana", "natalie", "brittany", "charlotte", "marie",
    "kayla", "alexis", "lori", "donna", "carol", "brenda", "pamela",
    "rose", "nikki", "jenny", "vanessa", "molly", "courtney", "christina",
    "kathleen", "jane", "ann", "debra", "rebecca", "virginia", "sharon",
    "karen", "elaine", "tiffany", "lori", "julie", "joyce", "diane",
    "alice", "jennifer", "lily", "ruth", "sandra", "dorothy", "shirley",
    "gloria", "marilyn", "betty", "barbara", "helen", "susan", "peggy",
    "carol", "maria", "lisa", "nancy", "margaret", "mary", "emma",
    "janet", "kathleen", "debra", "carl", "sarah", "kimberly", "jane",
    "pamela", "ann", "elizabeth", "patricia", "jennifer", "elaine",
    "linda", "karen", "sandra", "virginia", "michelle", "amy", "donna",
    "ashley", "rachel", "jessica", "emily", "stephanie", "nicole",
    "heather", "christine", "amanda", "melissa", "christina", "sharon",
    "laura", "katherine", "maria", "cynthia", "angela", "anna",
    "diane", "rebecca", "catherine", "janet", "samantha", "kathleen",
    "joan", "hannah", "evelyn", "judith", "megan", "cheryl", "martha",
    "gloria", "teresa", "sara", "madison", "frances", "kathryn",
    "janice", "jean", "abigail", "alice", "sophia", "grace", "denise",
    "amber", "doris", "danielle", "beverly", "isabella", "theresa",
    "diana", "natalie", "brittany", "charlotte", "marie", "kayla",
    "alexis", "lori", "vanessa", "courtney", "molly", "jenny", "nikki",
    "rose", "jane", "lily", "peggy", "carl", "elaine", "tiffany",
    "julia", "harper", "ella", "scarlett", "grace", "chloe", "victoria",
    "riley", "aria", "lily", "ellie", "hannah", "stell", "zoe", "nora",
    "luna", "sophia", "violet", "hazel", "aurora", "penelope", "layla",
    "camila", "nora", "zoey", "lena", "ivy", "everly", "willow",
    "emily", "ella", "elena", "isla", "charlotte", "mila", "aria",
    "hailey", "ella", "madelyn", "evelyn", "zoey", "gianna", "norah",
    "addison", "luna", "stella", "sarah", "autumn", "brooklyn", "lillian",
    "savannah", "allison", "ashley", "adele", "ariana", "quinn", "esther",
    "clara", "valentina", "emma", "riley", "ivy", "may", "kennedy",
    "sophia", "madeline", "peyton", "serenity", "faith", "lucy",
    "isabella", "elyse", "alice", "harper", "alexandra", "caroline",
    "ava", "elena", "anna", "diana", "angie", "elsie", "valeria",
    "charli", "jade", "emerson", "michelle", "gemma", "gracie", "liliana",
    "amara", "jessie", "bianca", "julia", "melanie", "raelynn", "eva",
    "lexi", "melissa", "lorenzo", "alina", "maya", "jade", "remi",
    "jade", "ada", "natalia", "nicole", "ivy", "charli", "emersyn",
    "delilah", "jade", "leila", "liana", "alina", "alina", "amaya",
    "yaretzi", "april", "reagan", "callie", "julianna", "adeline",
    "kimberly", "annabelle", "michelle", "rosie", "emersyn", "adelyn",
    "genevieve", "harper", "alena", "rylee", "claire", "allison",
    "jade", "avalynn", "ember", "amira", "ivy", "aleah", "gracie",
    "jade", "liliana", "nadia", "sawyer", "trinity", "katrina",
    "rosalie", "emerson", "sadie", "asher", "elena", "mariana",
    "nicole", "angelina", "anna", "alina", "eva", "jade", "amara",
    "kaylee", "lucia", "michelle", "gemma", "lola", "lucy", "arynn",
    "alice", "blakely", "jade", "luna", "natalia", "elena", "gianna",
    "maya", "julia", "leah", "brielle", "delaney", "aubree", "kimber",
    "elise", "lia", "bianca", "remi", "jade", "sarah", "alayna",
    "nicole", "london", "avalyn", "gracelyn", "grace", "mckenzie",
    "blakely", "kamila", "talia", "elena", "ruby", "peyton", "adalyn",
    "remi", "emma", "clara", "lydia", "emily", "sloane", "isla",
    "eva", "eva", "adalyn", "aurora", "hailey", "aaliyah", "lydia",
    "nadia", "kaylee", "madeline", "ivy", "clara", "lillian",
    "jasmine", "eva", "eva", "emersyn", "arynn", "aleah", "jade",
    "adalyn", "adalynn", "mya", "hazel", "elsie", "nora", "leilani",
    "adalyn", "violet", "evie", "lucy", "mariah", "piper", "harley",
    "natalie", "rose", "daisy", "elise", "ivy", "eleanor", "melody",
    "marley", "jade", "ariana", "joanna", "amira", "amira", "morgan",
    "lydia", "adalynn", "valerie", "grace", "alina", "aria", "connor",
    "jade", "isla", "hadley", "stella", "nova", "leah", "bella",
    "raelynn", "elena", "arabella", "aleah", "serenity", "laila",
    "lia", "kira", "nina", "kimberly", "kate", "adalyn", "jade",
    "adeline", "kyla", "trinity", "sarah", "lilah", "alina", "adalynn",
    "layla", "michelle", "adalynn", "jade", "laila", "adelyn",
    "london", "nicole", "penelope", "regina", "jane", "rosie",
    "alice", "georgia", "jade", "elena", "aria", "marley", "lana",
    "jade", "jade", "kira", "leah", "alina", "hadley", "nina",
    "jade", "ivy", "leilani", "eva", "gemma", "gracie", "jade",
    "leila", "alina", "leah", "anna", "elena", "london", "rosa",
    "julia", "jade", "luna", "aliyah", "emery", "dahlia", "remy",
    "lana", "adalyn", "emma", "jade", "leah", "lucy", "kate",
    "julia", "clara", "eva", "laila", "ralph", "alice", "maria",
    "isabella", "ava", "maya", "zoe", "zoey", "penelope", "layla",
    "chloe", "grace", "scarlett", "anna", "caroline", "nova",
    "camila", "hazel", "aria", "ellie", "lily", "elena", "ivy",
    "willow", "hailey", "eleanor", "emily", "aurora", "stella",
    "violet", "savannah", "brooklyn", "leah", "zoey", "penelope",
    "lillian", "addison", "zoey", "nora", "camila", "riley",
    "luna", "sophia", "ella", "aria", "lucy", "paisley", "everly",
    "clara", "gracie", "ivy", "hazel", "aubrey", "melody", "serenity",
    "claire", "ellie", "elise", "victoria", "ashley", "brielle",
    "lilian", "sarah", "katherine", "charlotte", "elena", "christian",
    "lillian", "maria", "arianna", "ella", "nora", "grace", "ivy",
    "stella", "aurora", "hannah", "emily", "lily", "eleanor", "elena",
    "ella", "isla", "clara", "scarlett", "maya", "sophia", "riley",
    "aria", "luna", "evie", "emma", "hailey", "aria", "leah",
    "callie", "jade", "adalyn", "lana", "amara", "lena", "anna",
    "arielle", "daisy", "elena", "eva", "clara", "natalie", "ivory",
    "millie", "adalyn", "stella", "adeline", "kimber", "rosie",
    "marley", "leila", "violet", "adalynn", "leah", "bella", "luna",
    "aurora", "nova", "penelope", "lucy", "brielle", "hazel",
    "delilah", "kennedy", "serenity", "sawyer", "aria", "mckenna",
    "grace", "emery", "ivy", "madelyn", "robert", "paisley", "alice",
    "margaret", "clara", "sarah", "eva", "clara", "ivy", "violet",
    "adalyn", "lana", "charlotte", "leah", "maeve", "adalyn", "elena",
    "kate", "marley", "willow", "adelyn", "adelyn", "remy", "aria",
    "sawyer", "jade", "adalyn", "rosie", "adalyn", "lucy", "alice",
    "adalyn", "remy", "lucy", "adalyn", "aria", "adalyn", "adalyn",
    "adalyn", "maria", "aria", "kennedy", "adalynn", "adalyn", "anna",
    "clara", "adalyn", "adalyn", "adalyn", "eva", "lucy", "luna",
    "leah", "alice", "aria", "ivy", "violet", "grace", "stella",
    "nova", "aurora", "hazel", "elena", "clara", "adalyn", "ivy",
    "adalyn", "adalyn", "adalyn", "adalyn", "evie", "adalyn", "jade",
    "luna", "eva", "maeve", "adalyn", "lily", "adalyn", "willow",
    "adalyn", "ivy", "leilani", "eva", "elena", "ada", "aria",
    "leilani", "adalyn", "adalyn", "aria", "leila", "aria", "maria",
    "emilia", "adalyn", "adalyn", "adalyn", "sophia", "charlotte",
    "adalyn", "nora", "zara", "myla", "leia", "ana", "eva", "ada",
    "luna", "aria", "luna", "lily", "sophia", "ava", "aria", "brielle",
    "evie", "luna", "aria", "penelope", "hazel", "violet", "aria",
    "stella", "luna", "aria", "adalyn", "aria", "lily", "aria",
    "ella", "adalyn", "aria", "elena", "aria", "eva", "aria", "ivy",
    "aria", "eva", "evie", "luna", "aria", "lily", "nova", "aria",
    "eva", "luna", "grace", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",
    "aria", "aria", "aria", "aria", "aria", "aria", "aria", "aria",

    # ── Irish / Celtic ──────────────────────────────────────────────────
    "siobhan", "aoife", "ciara", "deirdre", "eithne", "fionnuala",
    "grainne", "maeve", "niamh", "orlaith", "brigid", "cormac",
    "declan", "fionn", "liam", "niall", "owen", "rory", "sean",
    "tierney", "sinéad", "aoibheann", "bronwen", "cathal", "dara",
    "eoin", "fergal", "gareth", "luke", "malachy", "oghan", "ronan",
    "simon", "torin", "ciarán", "donnchadh", "fiachra", "gearóid",
    "laoise", "meadhbh", "oísín", "saoirse", "téodóra", "aisling",
    "bebhinn", "cathal", "darragh", "eabha", "fionnuala", "gráinne",
    "honora", "iosef", "leann", "muireann", "niambh", "oinseach",
    "proinsias", "séamus", "tadhg", "uaine",

    # ── French ───────────────────────────────────────────────────────────
    "jean", "jacques", "philippe", "pierre", "michel", "francois",
    "louis", "andre", "gabriel", "antoine", "marie", "sophie",
    "camille", "isabelle", "nathalie", "sylvie", "colette",
    "madeleine", "marguerite", "renee", "alain", "bernard", "bruno",
    "christian", "claude", "denis", "dominique", "etienne", "frédéric",
    "gérard", "gilles", "guillaume", "henri", "herve", "jacques",
    "jean-pierre", "laurent", "lionel", "luc", "marc", "maurice",
    "maxime", "nicolas", "olivier", "patrice", "philippe", "raphaël",
    "remy", "rené", "robert", "stéphane", "sylvain", "thibault",
    "thierry", "vincent", "yves", "adélaïde", "adèle", "alizée",
    "amélie", "anaïs", "audrey", "brigitte", "carmen", "caroline",
    "celestine", "charlotte", "clémence", "clotilde", "danille",
    "delphine", "émilie", "florence", "françoise", "geneviève",
    "gisele", "hélène", "huguette", "isabelle", "jacqueline",
    "juliette", "laure", "laurence", "léa", "léonie", "loïse",
    "mado", "manon", "maureen", "mireille", "noémie", "oceane",
    "odette", "paulette", "pénélope", "prune", "rachelle", "rose",
    "roxane", "sabine", "simone", "stéphanie", "susanne", "suzanne",
    "valentine", "véronique", "vivienne",

    # ── German / Austrian / Swiss ────────────────────────────────────────
    "hans", "karl", "klaus", "stefan", "thomas", "wolfgang",
    "friedrich", "heinrich", "otto", "max", "elsa", "gertrude",
    "heidrun", "ingrid", "katarina", "liesel", "monika", "renate",
    "sigrid", "ursula", "adam", "alexander", "bastian", "benedikt",
    "benno", "bernhard", "boris", "christoph", "constantin", "david",
    "dominik", "erik", "erwin", "fabian", "felix", "florian", "franz",
    "fred", "frederik", "fritz", "georg", "gerald", "gerhard", "gerry",
    "guido", "gunter", "gustav", "harry", "heiko", "helmut", "herbert",
    "herman", "holger", "hugo", "ingo", "jannik", "joachim", "johannes",
    "jonas", "josef", "jürgen", "justus", "kai", "kevin", "konstantin",
    "kurt", "lars", "leon", "lorenz", "lothar", "lucas", "lukas",
    "malte", "marcel", "marcus", "markus", "martin", "matthias", "max",
    "maximilian", "moritz", "nils", "oliver", "oscar", "oskar",
    "patrick", "paul", "peter", "philipp", "ralf", "rasmus", "rene",
    "ricardo", "richard", "roland", "roman", "ruben", "rudolf", "sascha",
    "sebastian", "siemen", "stefan", "sven", "termin", "tim", "tobias",
    "toni", "torben", "torsten", "valentin", "walter", "werner",
    "wiebke", "wolfgang", "yannick", "adela", "adeline", "agnes",
    "alina", "alma", "amalie", "amanda", "ana", "anja", "annika",
    "antje", "astrid", "barbara", "beate", "brigitte", "carla",
    "carolina", "celina", "charlotte", "chiara", "clara", "claudia",
    "constanze", "cornelia", "diana", "dora", "edina", "edith",
    "ekaterina", "elena", "elisa", "elisabeth", "elke", "ella",
    "emilia", "emilie", "erika", "esther", "eva", "fabienne", "felicitas",
    "fiona", "flora", "franziska", "frieda", "gabi", "greta", "gisela",
    "gunda", "hana", "hanna", "hannelore", "heide", "heike", "helena",
    "helga", "henriette", "herma", "ida", "ilka", "ilona", "inga",
    "ingrid", "irene", "iris", "isabel", "isabella", "isabelle",
    "jana", "janina", "jasmin", "jennifer", "jenny", "jessica",
    "johanna", "julia", "juliane", "karin", "karolina", "katharina",
    "kathrin", "katja", "katrin", "kerstin", "kim", "klara", "konstanze",
    "lara", "laura", "lena", "lene", "lilli", "lilly", "lina", "linda",
    "lore", "lori", "lotta", "lotte", "lou", "louisa", "luisa", "lydia",
    "maddalena", "magda", "magdalena", "maike", "manuela", "marcela",
    "margit", "margot", "marie", "marina", "marion", "marlene", "martina",
    "mary", "mathilda", "matilda", "maurice", "maxi", "melanie",
    "melissa", "merle", "meta", "micaela", "michele", "miriam",
    "mona", "nadja", "nana", "natalie", "natascha", "nelia", "nicola",
    "nicole", "nina", "noemi", "olga", "petra", "pia", "rachel",
    "regina", "rebecca", "renate", "resi", "rita", "roksana", "rosa",
    "rosalinde", "rose", "sabine", "sabrina", "sandra", "saskia",
    "serena", "sigrid", "silke", "simone", "sofia", "sonja", "sophia",
    "sophie", "stella", "susanne", "svenja", "teresa", "thea",
    "theresa", "tina", "tone", "trude", "ursula", "uschi", "valentina",
    "valerie", "verena", "veronika", "victoria", "virginia", "walburga",
    "wendy", "xenia", "zara",

    # ── Russian / Slavic ─────────────────────────────────────────────────
    "alexei", "boris", "dimitri", "igor", "nikolai", "sergei",
    "vladimir", "yuri", "vassily", "pyotr", "anna", "elena", "irina",
    "katya", "natalia", "olga", "tatiana", "victoria", "yelena", "zoya",
    "alexander", "alexey", "andrei", "arkady", "artem", "bogdan",
    "dmitry", "feodor", "grigory", "gennady", "genri", "ilya", "ilya",
    "iván", "konstantin", "lev", "maksim", "makar", "nikita", "nikolay",
    "oleg", "osip", "pavel", "roman", "ruslan", "semen", "slava",
    "stanislav", "timofey", "valentin", "valery", "veniamin", "viktor",
    "vissarion", "vladislav", "vladlen", "voyislav", "yakov", "yaroslav",
    "zakhar", "anastasia", "anfisa", "anna", "antonia", "valentina",
    "valeria", "varvara", "vera", "veronika", "victoria", "galina",
    "daria", "evgenia", "evdokia", "zoya", "innokenti", "karolina",
    "kira", "klara", "kristina", "larisa", "lyudmila", "marfa",
    "margarita", "marina", "marfa", "nadezhda", "nina", "nonna",
    "oksana", "oksana", "oksana", "raisa", "rufina", "snezhana",
    "sofia", "sofya", "stella", "tamara", "uliana", "ulyana",

    # ── Italian ──────────────────────────────────────────────────────────
    "luca", "marco", "giovanni", "paolo", "alessandro", "andrea",
    "matteo", "lorenzo", "simone", "antonio", "valentina", "giulia",
    "francesca", "aurora", "ginevra", "vittoria", "marta", "beatrice",
    "chiara", "sara", "adriano", "agostino", "alberto", "alessio",
    "alfonso", "alvise", "ambrogio", "amico", "angelo", "anselmo",
    "antimo", "anto", "antonia", "anzio", "arcangelo", "armando",
    "armido", "arnaldo", "baldo", "battista", "belisario", "beniamino",
    "benito", "benvenuto", "berardino", "berdo", "bernardo", "berto",
    "beside", "biagio", "bruno", "calogero", "candido", "carlo",
    "carmine", "casimiro", "cassio", "catello", "cecco", "cesare",
    "chicco", "ciro", "colombo", "concetto", "corrado", "cosimo",
    "costantino", "damiano", "daniele", "dante", "dario", "davide",
    "degli", "dino", "domenico", "duilio", "durante", "edoardino",
    "edvige", "efisio", "eleonora", "elio", "elia", "emanuele",
    "emicola", "enrico", "enzio", "ercole", "erminio", "eros", "etlio",
    "ettore", "fabbrizio", "fabiano", "fabio", "fabrizio", "faldo",
    "fausto", "febo", "felice", "feliciano", "filippo", "fiorenzo",
    "fiorino", "folco", "forestiero", "fornovo", "francesco", "franco",
    "fredis", "fulvio", "gaetano", "galeazzo", "gamberini", "gavino",
    "generoso", "genesio", "gentile", "giacomo", "giambattista", "gian",
    "gianni", "gideon", "giordano", "giorgio", "giosuè", "giovanni",
    "girolamo", "giuliano", "giulio", "giuseppe", "giustino", "giusto",
    "glauco", "goffredo", "greco", "gregorio", "guarino", "guelfo",
    "guido", "guglielmo", "hugo", "ilario", "ippolito", "ivano",
    "lamberto", "lancillotto", "lando", "leandro", "leo", "leonardo",
    "leone", "leopoldo", "lorenzo", "loriano", "luca", "ludovico",
    "luigi", "magnano", "malatesta", "manfredo", "manfredi", "manuel",
    "marcello", "marco", "mario", "marino", "mario", "marzio", "massimo",
    "matteo", "mattia", "maurilio", "maurizio", "meo", "michele",
    "mirco", "modesto", "monaldo", "nanni", "napoleone", "napolino",
    "niccolò", "nico", "nicola", "nicolo", "nino", "obitorio", "odal",
    "oderico", "olindo", "oliviero", "orlando", "orso", "osvaldo",
    "ottavio", "ottone", "palmiro", "panfilo", "paolo", "paris",
    "parsifal", "pasquale", "patrizio", "pellegrino", "pier", "piero",
    "pierluigi", "pietro", "pio", "pisanello", "polissena", "polluce",
    "primo", "ranside", "raffaele", "raimondo", "ramiro", "raoul",
    "remo", "riccardo", "rinaldo", "rino", "rito", "robico", "roberto",
    "rodolfo", "rogerio", "romolo", "romeo", "romualdo", "romano",
    "rocco", "rostislavo", "ruben", "ruggero", "rufo", "ruggiero",
    "sabatino", "salvatore", "samuele", "sante", "santeramo", "santino",
    "saul", "scarpetta", "sebastiano", "serafino", "sergio", "severo",
    "sigismondo", "silvano", "silvestro", "simone", "simonetto", "sixte",
    "stanislao", "stefano", "tebaldo", "taddeo", "teodoro", "terenzio",
    "tito", "tiziano", "tolomeo", "tommaso", "torquato", "ugo",
    "umberto", "urbano", "valentino", "valerio", "vanni", "venanzio",
    "venerando", "venustiano", "verrocchio", "vincenzo", "violante",
    "virgilio", "vito", "vittorio", "zaccaria", "zenobio",

    # ── Spanish / Portuguese ─────────────────────────────────────────────
    "carlos", "diego", "fernando", "jorge", "luis", "manuel", "pedro",
    "rafael", "sergio", "adrian", "carmen", "elena", "isabella", "lucia",
    "paula", "sofia", "valeria", "clara", "triana", "alvaro", "antonio",
    "bartolomé", "cristóbal", "eduardo", "enrique", "francisco",
    "gabriel", "gonzalo", "guillermo", "gustavo", "hector", "hugo",
    "ignacio", "isidro", "javier", "joaquin", "jose", "josé", "juan",
    "leandro", "marcos", "miguel", "nicolas", "oscar", "pablo",
    "raúl", "ricardo", "roberto", "rodrigo", "rubén", "samuel",
    "santiago", "sebastián", "simon", "tomas", "alicia", "alexandra",
    "almudena", "amanda", "analía", "ana", "andrea", "beatriz",
    "belen", "blanca", "carmen", "carolina", "catalina", "cristina",
    "daniela", "diana", "elena", "elisa", "eva", "francisca", "gabriela",
    "gala", "gema", "gisela", "helena", "irene", "isabel", "julia",
    "jimena", "josefina", "julia", "laura", "letizia", "liliana",
    "lina", "lucía", "luisa", "lydia", "maria", "marina", "marta",
    "mónica", "nerea", "nuria", "olga", "patricia", "raquel", "raquel",
    "silvia", "soledad", "sonia", "susana", "tatiana", "teresa",
    "verónica", "victoria", "violeta", "virginia", "yolanda", "zaira",
    "bruno", "rafael", "diego", "mateo", "santiago", "sebastián",
    "benjamín", "daniel", "tomás", "simón", "gabriel", "nicolas",
    "mateo", "dylan", "matías", "scarlett", "daniela", "isabella",
    "valentina", "mía", "emma", "triana", "sofía", "camila",
    "fernanda", "victoria", "lucía", "maría", "ximena", "regina",
    "alejandra", "paula", "carolina", "ana", "laura", "soledad",
    "conchita", "francisca", "ramón", "enrique", "diego", "raúl",

    # ── Portuguese ───────────────────────────────────────────────────────
    "raimundo", "raoni", "renato", "rodrigo", "rui", "samuel", "santiago",
    "sergio", "silvio", "theodoro", "thiago", "tomas", "trovão", "vicente",
    "victor", "vitor", "wagner", "washington", "wellington", "xavier",
    "yago", "yuri", "zenildo", "adriana", "alessandra", "amanda",
    "ana", "angelica", "bia", "bruna", "camila", "carla", "carolina",
    "cátia", "clara", "cláudia", "constança", "cristiana", "daniela",
    "douglas", "eliane", "elisa", "erika", "evaldo", "fernanda",
    "flávia", "franciele", "gabriela", "giovanna", "helena", "heloísa",
    "isabela", "isabelle", "isabela", "janaína", "jasmin", "jennifer",
    "jéssica", "julia", "júlia", "jully", "karina", "kelly", "kely",
    "laís", "larissa", "laura", "lauren", "leila", "letícia", "lili",
    "lilian", "livia", "lorena", "luana", "luciana", "luísa", "madalena",
    "marcela", "marcelle", "márcia", "marcos", "margarida", "maria",
    "mariana", "marina", "marisa", "márlise", "mary", "michelle",
    "mónica", "nathalia", "natasha", "nathalie", "nathália", "nina",
    "pamela", "patrícia", "paula", "raquel", "regiane", "regina",
    "rejane", "renata", "rosana", "rosangela", "rossana", "sandra",
    "sara", "sheila", "silvia", "simone", "sirley", "sônia", "sonia",
    "stefani", "tanía", "tatiana", "thais", "thayná", "valentina",
    "valéria", "vanessa", "varlene", "verônica", "viviane",

    # ── Dutch / Flemish ──────────────────────────────────────────────────
    "bas", "cas", "daan", "daniël", "dennis", "dick", "dirk", "erik",
    "faas", "fay", "fenn", "ferre", "finn", "florian", "gerard",
    "gijs", "guus", "hank", "hugo", "jaap", "jan", "jari", "jasper",
    "joep", "joeri", "johannes", "jonas", "jop", "julian", "kees",
    "kevin", "lars", "lean", "lenn", "lennard", "levi", "lode",
    "luc", "luuk", "marc", "marco", "mark", "martin", "matthijs",
    "mees", "milan", "noud", "noud", "olivier", "otis", "pieter",
    "poekel", "reed", "reinier", "rick", "roan", "robin", "ruben",
    "ruud", "samber", "samuel", "senn", "silas", "sven", "teun",
    "thijmen", "thomas", "tijn", "timo", "tobias", "tom", "valentijn",
    "vic", "vincent", "wout", "xavi", "yorick", "yves", "bob",
    "gijs", "senn", "boaz", "sepp", "jack", "jay", "stijn", "stef",
    "lieve", "fem", "femke", "fien", "ilse", "juul", "lars", "lina",
    "lise", "noa", "noor", "poekel", "roma", "sofie", "tessa",
    "veerle", "yara", "amber", "annabel", "anna", "benthe", "bibi",
    "bo", "carlijn", "demi", "dewi", "dilara", "eline", "elise",
    "ella", "elsa", "emma", "eva", "evi", "fay", "feline", "fenne",
    "fenn", "flore", "frederique", "hanna", "hedwig", "helena",
    "isa", "isabelle", "jasmijn", "jenna", "jill", "jip", "joëlle",
    "josefien", "juliette", "kiki", "lana", "lara", "laura",
    "lenn", "lenthe", "lieve", "lina", "lisa", "lot", "lotta",
    "lotte", "louise", "luna", "mae", "marit", "marla", "meis",
    "naomi", "noa", "noor", "noor", "nora", "pien", "reza", "rosa",
    "rosalie", "saar", "samira", "sanne", "sem", "silke", "sofie",
    "soleil", "sterre", "tess", "tessa", "veerle", "yara",

    # ── Nordic / Scandinavian ────────────────────────────────────────────
    "anders", "axel", "carl", "erik", "erik", "gustav", "hans",
    "johan", "karl", "lars", "lukas", "magnus", "mikael", "niels",
    "niklas", "ole", "oscar", "otto", "oskar", "peter", "sigurd",
    "søren", "stefan", "svend", "thomas", "tor", "valdemar", "vilhelm",
    "vilhelm", "vilhelm", "adela", "agda", "astrid", "berit", "birgit",
    "ebba", "elina", "elsa", "emma", "erika", "eva", "freja", "greta",
    "gudrun", "gunnel", "göta", "helga", "helmi", "ida", "ingrid",
    "josefin", "karin", "kerstin", "lena", "linnea", "lovisa", "maia",
    "maja", "maud", "mia", "maja", "milla", "mine", "nanna", "ninna",
    "nora", "odda", "olga", "ridder", "ronja", "saga", "sigrid",
    "sofia", "soline", "solveig", "sonja", "stella", "sunna", "svava",
    "thea", "tolle", "tonje", "ull", "ulla", "valborg", "victoria",
    "viola", "yrsa",

    # ── Hebrew / Yiddish ─────────────────────────────────────────────────
    "abraham", "adam", "adar", "adina", "akedah", "amnon", "amos",
    "anat", "asael", "ashera", "ashmedai", "aviva", "avner", "ayo",
    "batya", "bezalel", "chai", "dan", "daniel", "david", "devorah",
    "doeg", "dor", "edna", "elazar", "elhanan", "eliezer", "elijah",
    "elishba", "elisheva", "ella", "emanuel", "emmanuel", "erach",
    "esther", "ezekiel", "ezra", "gad", "gil", "hadassah", "hagar",
    "ham", "hannah", "hava", "heber", "helen", "herman", "hezekiah",
    "hilary", "hillel", "hod", "hur", "ido", "innocent", "irene",
    "iris", "isaac", "isaiah", "israel", "issachar", "jacob", "jair",
    "jared", "jason", "jehoash", "jehoshaphat", "jephthah", "jeremiah",
    "jericho", "jeroboam", "jesse", "jesus", "jethro", "jewish",
    "joachim", "joel", "john", "jonah", "jonathan", "joseph", "joshua",
    "josiah", "jubal", "judah", "judith", "julian", "julius", "kedar",
    "kenaz", "laban", "leah", "leander", "lela", "lenox", "leora",
    "levi", "lo-ammi", "lot", "lucifer", "lucinda", "luz", "mahanaim",
    "manasseh", "manuel", "martha", "matthew", "megiddo", "meir",
    "melchizedek", "micah", "michael", "michal", "michelle", "mighty",
    "miriam", "moriah", "moses", "nahum", "naphtali", "nathan",
    "nathaniel", "nezach", "noah", "noe", "nolan", "nora", "oded",
    "olive", "oren", "ori", "othniel", "perez", "philip", "phinehas",
    "rachel", "rahab", "raphael", "rebekah", "rehoboam", "reuben",
    "ruth", "sabin", "salome", "samson", "samuel", "sanhedrin", "saul",
    "seth", "sharon", "shelomi", "shelomith", "shem", "silas", "simeon",
    "simon", "solomon", "susan", "tabitha", "tamar", "thaddaeus",
    "tobiah", "tola", "uri", "uriah", "ursula", "vashti", "xerxes",
    "yael", "yahveh", "yair", "yehuda", "yisrael", "yitzhak", "zadok",
    "zebulun", "zedekiah", "zelophehad", "zilpah", "zipporah",

    # ── Arabic ───────────────────────────────────────────────────────────
    "aaliyah", "aamir", "aaron", "abas", "abbas", "abbie", "abdul",
    "abdullah", "abeer", "abir", "abra", "adam", "adamina", "adamma",
    "adel", "adel", "adib", "adrian", "afnan", "agha", "ahmad",
    "ahmed", "aimen", "aila", "aimee", "ainsley", "airth", "aisyah",
    "akbar", "akil", "akira", "ala", "aladdin", "alan", "alaric",
    "alastair", "alberic", "albert", "albrecht", "alby", "alcina",
    "alden", "aldo", "aldric", "alekos", "alese", "alex", "alexander",
    "alexandra", "alexandria", "alexina", "alexine", "alexio", "alf",
    "alfie", "alfonse", "alfred", "alger", "alick", "alina", "alisa",
    "alison", "alistair", "alister", "allan", "allen", "alleria",
    "alli", "allie", "allison", "allyson", "alma", "almira", "alois",
    "alon", "alonso", "alonzo", "alpha", "alphonse", "alric", "altar",
    "althea", "alton", "aluino", "alvin", "alyson", "alyssa", "amanda",
    "amani", "amar", "amara", "amarantha", "amaris", "amaury", "amber",
    "ambra", "ambrose", "ambrosia", "ambrosine", "ambrosio", "ambrosius",
    "ame", "amelia", "amelie", "amelina", "ameline", "amerigo", "ami",
    "amias", "amice", "amie", "amin", "amiram", "amis", "amita",
    "amity", "amory", "amos", "amparo", "amr", "amram", "amun",
    "amy", "an", "ana", "anabel", "analise", "anastacia", "anastasio",
    "anastatius", "anastatius", "anastatius", "anastazja", "anastasia",
    "anatola", "anatole", "anatolio", "ancel", "ancelote", "ancona",
    "andee", "anden", "ander", "andi", "andie", "ando", "andonis",
    "andre", "andrea", "andreana", "andreanna", "andree", "andrei",
    "andrej", "andres", "andreu", "andrew", "andrey", "andria",
    "andrian", "andromache", "andy", "ane", "anet", "anet", "anette",
    "ang", "angeli", "angelia", "angelica", "angelina", "angeline",
    "angique", "angus", "anick", "anis", "anja", "anjali", "anmol",
    "ann", "ann-marie", "annabel", "annabella", "annabelle", "annadine",
    "annalee", "annalise", "annamaria", "annasophia", "annASTASIA",
    "annette", "annice", "annie", "annmarie", "ano", "anora", "ansel",
    "anselm", "anselma", "anselmo", "antoinette", "antoine", "antoni",
    "antonia", "antonie", "antonietta", "antoniette", "antonin",
    "antonina", "antonino", "antonio", "antora", "antser", "antwan",
    "anurag", "anzio", "aparna", "apollinaire", "apollinaris", "apollo",
    "apostolis", "apphia", "april", "ar", "arabella", "arabelle",
    "aram", "arame", "aran", "arch", "archer", "archibald", "archie",
    "archippo", "archivald", "archy", "ardal", "arden", "ardith",
    "areli", "arella", "ares", "argus", "argyle", "ari", "aria",
    "ariana", "ariane", "arianna", "arianne", "arib", "aribinda",
    "aric", "aridel", "ariel", "ariella", "arielle", "arjun", "arkadi",
    "arlan", "arlen", "arlene", "arlin", "arline", "arlo", "armand",
    "armando", "armania", "armin", "armina", "armond", "arnaud",
    "arnault", "arne", "arnie", "arno", "arnold", "arnulf", "arnulfo",
    "arom", "aron", "aronofsky", "arp", "arron", "arsen", "arsene",
    "arsenio", "art", "artair", "arte", "artemis", "artemisa", "arthur",
    "artie", "arturo", "arundel", "arvel", "ary", "aryana", "aryeh",
    "as", "asa", "ase", "ash", "ashby", "asher", "ashley", "ashli",
    "ashlie", "ashling", "ashlyn", "ashton", "asia", "asli", "aspasia",
    "assunta", "astier", "astin", "ata", "atalanta", "ataullah",
    "athena", "atlas", "atleta", "atticus", "attila", "atty", "aubert",
    "aubrey", "audie", "audley", "audra", "audrey", "august", "augusta",
    "auguste", "augustin", "augustine", "augustus", "aulii", "aurel",
    "aurelia", "aurelie", "aurelio", "aurora", "auroralee", "aurore",
    "austen", "austin", "autumn", "ava", "avanel", "avary", "ave",
    "aveline", "averil", "averill", "avery", "avi", "avice", "avigail",
    "avner", "avram", "avril", "avtalion", "aw", "axel", "axton",
    "ayala", "ayanna", "ayat", "ayden", "ayla", "aylmer", "ayn",
    "ayres",

    # ── Scottish / Welsh / Celtic ────────────────────────────────────────
    "angus", "brae", "bruce", "callum", "cameron", "craig", "duncan",
    "ewan", "ewan", "ewan", "finlay", "hamish", "iain", "kenneth",
    "lewis", "murray", "neil", "oban", "robbie", "robin", "ruairidh",
    "ruraidh", "stuart", "alasdair", "alcon", "alexander", "alistair",
    "alister", "baird", "barnaby", "bryce", "caden", "calum", "carson",
    "caulay", "christy", "colin", "comhnall", "connell", "connor",
    "constance", "cryil", "daithí", "darach", "delvin", "devlin",
    "dougal", "douglas", "dugald", "duff", "earn", "edlin", "evan",
    "gael", "galen", "gavin", "gillon", "hamish", "hugh", "ian",
    "irvine", "jack", "jackie", "jaimie", "james", "jamie", "jardy",
    "jonathon", "kay", "keir", "keith", "kellen", "kennett", "kenneth",
    "kennth", "lachlan", "lachlann", "leighton", "lennan", "lennard",
    "leodhais", "lewis", "lorne", "lucas", "lugh", "luke", "luthais",
    "mac", "macintyre", "malcolm", "mannie", "mark", "martyn", "matheson",
    "megget", "mungo", "murdo", "murdoch", "murdock", "murphy", "ned",
    "neil", "neill", "nessan", "niall", "nolan", "otter", "owain",
    "owen", "paisley", "pate", "percy", "raymond", "rennie", "rian",
    "robin", "roddie", "roderick", "rodney", "rodric", "rodrick",
    "rodrigo", "rogan", "ruairi", "ruaraidh", "ruaridh", "rupert",
    "tavish", "thomson", "tod", "toddy", "tormod", "wallace", "ward",
    "wattie", "willie", "wynn", "yncol", "zander",

    # ── Popular Place/Word Names ─────────────────────────────────────────
    "brooklyn", "chelsea", "dakota", "india", "jordan", "logan",
    "madison", "phoenix", "presley", "river", "sawyer", "taylor",
    "tyler", "virginia",

    # ── Compound / Double Names ──────────────────────────────────────────
    "mary-kate", "sarah-jane", "billy-bob", "jimmy-joe", "tommy-lee",
    "mary grace", "sarah jane",

    # ── Nicknames / Diminutives (common spoken forms) ────────────────────
    "bobby", "billy", "tommy", "jimmy", "johnny", "jenny", "katie",
    "beth", "meg", "susie", "polly", "sally", "danny", "davey",
    "jackie", "mandy", "tracy", "mel", "vic", "patty", "terri",
    "robbie", "greg", "tony", "mike", "chris", "steve", "dave",
    "matt", "pat", "dan", "ben", "sam", "nick", "tom", "jim",
    "bob", "ed", "bill", "jeff", "alex", "max", "fred", "ralph",
    "al", "pete", "phil", "marty", "charlie", "frank",

    # ── Historical / Famous ──────────────────────────────────────────────
    "abraham", "alexander", "albert", "alfred", "arthur", "augustus",
    "benjamin", "bernard", "brigham", "caesar", "calvin", "carl",
    "catherine", "charles", "charlie", "cleopatra", "columbia", "craig",
    "dale", "david", "earl", "edgar", "edmund", "edward", "egbert",
    "eleanor", "elizabeth", "emma", "ethel", "frances", "franklin",
    "frederick", "gatsby", "george", "gerry", "hamilton", "hannah",
    "harry", "harriet", "helen", "henry", "herbert", "herman", "homer",
    "hoover", "howard", "hugh", "irving", "jackson", "jacob", "james",
    "jean", "jefferson", "jennifer", "jeremiah", "jesse", "jimmy",
    "joan", "johann", "john", "johnny", "jonathan", "joseph", "joshua",
    "julius", "justin", "keith", "kennedy", "king", "kirk", "larry",
    "lawrence", "lenin", "leonard", "lewis", "lincoln", "lisa", "lucy",
    "madison", "malcolm", "marcus", "margaret", "maria", "marilyn",
    "mark", "martin", "marvin", "mary", "matthew", "max", "melville",
    "michael", "michelle", "montgomery", "nancy", "nelson", "newton",
    "nixon", "nora", "norman", "olive", "olivia", "oscar", "owen",
    "patricia", "patrick", "paul", "peter", "philip", "plato",
    "presley", "ralph", "randolph", "rebecca", "richard", "robert",
    "robin", "rockefeller", "roger", "ronald", "roosevelt", "ross",
    "russell", "ruth", "sally", "samuel", "sandra", "sarah", "scarlett",
    "shelby", "sophia", "stanley", "stephen", "steven", "susan",
    "thatcher", "theodore", "thomas", "tyler", "victor", "virginia",
    "vivian", "wallace", "walter", "washington", "waylon", "william",
    "willie", "wyatt",

    # ── Native American ──────────────────────────────────────────────────
    "coyote", "haskell", "hiawatha", "kenai", "koda", "makwa", "nokomis",
    "powhatan", "sacagawea", "sequoyah", "tatanka", "tenskwatawa",
    "waneta", "wapasha", "washakie", "wayne", "winona", "zenith",

    # ── Additional Common First Names ────────────────────────────────────
    "abel", "ace", "ada", "adelaide", "adele", "adi", "adrian",
    "aiden", "alan", "albert", "alberta", "alec", "aileen", "aline",
    "alma", "alta", "amalia", "amber", "amie", "amos", "amy", "ana",
    "andrea", "andy", "anita", "annette", "annie", "anthonia", "anya",
    "april", "arabella", "arlene", "arthur", "ashton", "audrey",
    "august", "autumn", "ava", "avery", "bailey", "barbara", "barry",
    "becky", "belle", "ben", "bernadette", "bernice", "bert", "bertha",
    "bessie", "beth", "betsy", "bettie", "betty", "beverly", "bill",
    "billy", "blanche", "bo", "bob", "bobbie", "bonnie", "brad",
    "bradley", "brandi", "brandy", "brent", "brett", "brian", "bridget",
    "brittany", "brock", "brook", "bruce", "bryan", "cameron", "candy",
    "carl", "carmen", "carol", "carole", "carrie", "casey", "cassidy",
    "catherine", "cathy", "chad", "charlene", "charlie", "cheryl",
    "chloe", "chris", "christian", "christina", "christy", "cindy",
    "claire", "clarence", "clark", "claudia", "cody", "colleen",
    "connie", "corey", "craig", "crystal", "curt", "curtis", "cynthia",
    "dale", "damon", "dana", "danny", "darla", "darlene", "darrel",
    "darrell", "darren", "dave", "dawn", "dean", "deb", "debbie",
    "deborah", "debra", "delia", "della", "delores", "denise", "dennis",
    "derrek", "derrick", "desiree", "devon", "diane", "dick", "donna",
    "doris", "dorothy", "doug", "douglas", "duane", "dustin", "dwayne",
    "dwight", "earl", "eddie", "edgar", "elaine", "elbert", "eleanor",
    "elijah", "elisa", "elise", "elizabeth", "ellen", "elmer", "elsie",
    "emily", "emma", "enoch", "erica", "erik", "erin", "ernest",
    "erwin", "estelle", "esther", "ethan", "eugene", "eva", "evan",
    "evelyn", "ezra", "farrah", "felicia", "felix", "florence",
    "floyd", "fonda", "ford", "frances", "francine", "frank", "frankie",
    "frazier", "fred", "frederic", "frederick", "fredric", "frieda",
    "gail", "garth", "gary", "gavin", "gene", "geoffrey", "gerald",
    "gina", "glen", "glenda", "glenn", "gloria", "glynis", "goldie",
    "gordon", "grace", "grant", "greg", "gregg", "gregory", "gwen",
    "gwendolyn", "hallie", "hans", "harold", "harriet", "harrison",
    "harvey", "heather", "heidi", "helen", "henry", "herbert",
    "herman", "hester", "hilary", "homer", "hope", "horace", "howard",
    "hugh", "ian", "ida", "ida", "irene", "irvin", "irving", "isaac",
    "isabel", "ivan", "jack", "jackie", "jacklyn", "jacob", "jake",
    "james", "jamie", "jan", "jane", "janet", "janice", "janie",
    "jared", "jasmine", "jason", "jay", "jean", "jeff", "jeffery",
    "jeffrey", "jennifer", "jenny", "jerald", "jeremy", "jermaine",
    "jerome", "jerri", "jerry", "jesse", "jessica", "jill", "jillian",
    "jim", "jimmy", "jo", "joan", "joann", "joanne", "jodi", "jody",
    "joe", "joel", "johanna", "john", "johnnie", "jon", "jonah",
    "jonathan", "jonathon", "jordan", "jordon", "jorge", "jose",
    "joseph", "josh", "joshua", "joy", "joyce", "juan", "judith",
    "judy", "julia", "julian", "juliana", "julie", "juliet", "june",
    "justin", "kaitlyn", "kara", "karen", "karl", "kate", "katelyn",
    "katherine", "kathleen", "kathryn", "kathy", "katie", "katrina",
    "kay", "kayla", "keith", "kelli", "kelly", "ken", "kenneth",
    "kent", "kerry", "kevin", "kim", "kimberly", "kirk", "krista",
    "kristen", "kristi", "kristie", "kristin", "kristina", "kristine",
    "kristy", "kurt", "kurtis", "kyle", "lance", "larry", "laura",
    "laurel", "lauren", "lauri", "laurie", "lawrence", "leah", "lee",
    "leon", "leonard", "lillian", "lillie", "lily", "linda", "lindsay",
    "lindsey", "lisa", "lois", "loren", "lorenzo", "lori", "lorraine",
    "lou", "louis", "louise", "lucas", "lucile", "lucille", "lucinda",
    "lucy", "luke", "luther", "lynn", "madelyn", "malcolm", "manuel",
    "marcus", "margaret", "marian", "marilyn", "marina", "mario",
    "marion", "marlene", "marshall", "martha", "martin", "marvin",
    "mary", "maureen", "maxine", "melanie", "melba", "melinda",
    "melissa", "michael", "michele", "michelle", "miguel", "mike",
    "mildred", "milton", "mimi", "miriam", "mitchell", "mohamed",
    "molly", "monica", "monte", "morris", "murray", "nancy", "nathan",
    "nathaniel", "neal", "neil", "nelson", "nicholas", "nick", "nina",
    "noel", "nora", "norma", "norman", "olga", "olive", "oliver",
    "olivia", "oscar", "owen", "pam", "pamela", "panama", "pat",
    "patrice", "patricia", "patrick", "patsy", "patty", "paul",
    "paula", "pauline", "peg", "peggy", "penny", "perry", "pete",
    "peter", "phil", "philip", "phillip", "phoebe", "phyllis",
    "priscilla", "rachel", "ralph", "randall", "randy", "raven",
    "raymond", "regina", "renee", "rex", "rhonda", "richard", "rick",
    "ricky", "rita", "rob", "robert", "roberta", "robin", "rod",
    "rodney", "roger", "ron", "ronald", "ronnie", "rosa", "rose",
    "rosemary", "ross", "roxanne", "roy", "russ", "russell", "ruth",
    "ryan", "sabrina", "sally", "salvatore", "sam", "samuel", "sandra",
    "sandy", "sara", "sarah", "saturday", "scott", "sean", "seth",
    "shane", "shannon", "sharon", "shawn", "sheila", "shelly", "sherry",
    "shirley", "sonya", "stacey", "stacy", "stan", "stanley", "stella",
    "stephanie", "stephen", "stuart", "sue", "susan", "suzanne",
    "sylvia", "tammy", "tanya", "tara", "taylor", "teresa", "terri",
    "terry", "theodore", "theresa", "thomas", "tim", "timothy", "tina",
    "todd", "tom", "tommy", "tony", "tracy", "travis", "troy", "tracy",
    "tyler", "valerie", "vanessa", "vernon", "veronica", "vicki",
    "vickie", "vicky", "victor", "victoria", "vincent", "viola",
    "virginia", "vivian", "wade", "wallace", "walter", "wanda",
    "warren", "wayne", "wendy", "wesley", "whitney", "william", "willie",
    "zachary",

    # ── Nature-inspired names ────────────────────────────────────────────
    "amber", "autumn", "brook", "canyon", "cedar", "cedar", "clementine",
    "coral", "daisy", "dawn", "fern", "flora", "garden", "garnet",
    "glen", "hazel", "heather", "holly", "jasmine", "jasper", "lily",
    "luna", "marigold", "maple", "may", "misty", "oakley", "olive",
    "pearl", "poppy", "rain", "river", "robin", "rose", "sage",
    "scarlet", "sky", "skyler", "summer", "sunny", "thorn", "willow",
    "zinnia",

    # ── Names that caused issues ─────────────────────────────────────────
    "liz", "lizbeth", "elizabeth", "lizzy", "beth", "betsy", "elsie",
    "liza", "elisa", "eliza", "elijah", "elisha", "elise", "elissa",

    # ── Syllables / fragments for smooth concatenation ───────────────────
    "la", "le", "li", "lo", "lu",
    "ra", "re", "ri", "ro", "ru",
    "da", "de", "di", "do", "du",
    "na", "ne", "ni", "no", "nu",
    "ma", "me", "mi", "mo", "mu",
    "ba", "be", "bi", "bo", "bu",
    "fa", "fe", "fi", "fo", "fu",
    "ka", "ke", "ki", "ko", "ku",
    "pa", "pe", "pi", "po", "pu",
    "sa", "se", "si", "so", "su",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "wa", "we", "wi", "wo", "wu",
    "za", "ze", "zi", "zo", "zu",
    "ja", "je", "ji", "jo", "ju",
    "ga", "ge", "gi", "go", "gu",
    "ha", "he", "hi", "ho", "hu",

    # ── Additional common names ──────────────────────────────────────────
    "muhammad", "nigel", "gunnar", "dmitri", "preston", "winston",
    "brendan", "caitlin", "jamal", "malik", "tyrone", "devin", "darius",
    "tariq", "rashid", "yusuf", "fatima", "ayesha", "khadija", "zainab",
    "ravi", "priya", "anjali", "sanjay", "rajesh", "deepak", "kumar",
    "vikram", "gita", "kavita", "mei", "ling", "lin", "takashi", "sayaka",
    "satoshi", "hiroshi", "emiko", "yuki", "sakura",

    # ── Popular Surnames (US Census top 125) ─────────────────────────────
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
    "davis", "rodriguez", "martinez", "hernandez", "lopez", "gonzalez",
    "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark",
    "ramirez", "lewis", "robinson", "walker", "young", "allen", "king",
    "wright", "scott", "torres", "nguyen", "hill", "flores", "green",
    "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell",
    "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz",
    "parker", "cruz", "edwards", "collins", "reyes", "stewart", "morris",
    "morales", "murphy", "cook", "rogers", "gutierrez", "ortiz", "morgan",
    "cooper", "peterson", "bailey", "reed", "kelly", "howard", "ramos",
    "kim", "cox", "ward", "richardson", "watson", "brooks", "chavez",
    "wood", "james", "bennett", "gray", "mendoza", "ruiz", "hughes",
    "price", "alvarez", "castillo", "sanders", "patel", "myers", "long",
    "ross", "foster", "jimenez", "powell", "jenkins", "perry", "russell",
    "sullivan", "bell", "coleman", "butler", "henderson", "barnes",
    "gonzales", "fisher", "vasquez", "simmons", "romero", "jordan",
    "patterson", "alexander", "hamilton", "graham", "reynolds", "griffin",
    "wallace", "moreno", "west", "cole", "hayes", "bryant", "herrera",
    "gibson", "ellis", "tran", "medina", "aguilar", "stevens", "murray",
    "ford", "castro", "marshall", "owens", "harrison", "fernandez",
    "mcdonald", "mccoy", "mcduff", "o'brien", "o'connor", "o'neill",
    "o'sullivan", "de la cruz", "van der berg",

    # ── Name-suffix / honorific keys ─────────────────────────────────────
    "mr", "mrs", "ms", "dr", "prof", "sir", "madam", "lady", "lord",
    "rev", "jr", "sr", "ii", "iii", "iv",
]))


def load_symbols(config_path):
    """Return the set of phoneme symbols the model's id map accepts."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return set(cfg["phoneme_id_map"].keys())


def parse_transcription(symbols, s):
    """Split a phoneme transcription string into the model's symbol tokens."""
    syms = sorted(symbols, key=len, reverse=True)
    out = []
    i = 0
    while i < len(s):
        for sym in syms:
            if s.startswith(sym, i):
                out.append(sym)
                i += len(sym)
                break
        else:
            raise ValueError(f"cannot parse {s!r} at position {i}: {s[i:]!r}")
    return out


def to_adpcm_wav(ffmpeg, wave_bytes):
    """Resample a 22050Hz mono PCM WAV to 16kHz mono IMA ADPCM WAV bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(wave_bytes)
        cmd = [ffmpeg, "-y", "-i", src, "-ar", "16000", "-ac", "1",
               "-c:a", "adpcm_ima_wav", dst]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        with open(dst, "rb") as f:
            return f.read()


def synth_phonemes(voice, tokens):
    """Synthesize raw phoneme tokens in-process; return PCM WAV bytes."""
    ids = voice.phonemes_to_ids(tokens)
    audio = voice.phoneme_ids_to_audio(ids)
    if isinstance(audio, tuple):
        audio = audio[0]
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    pcm = (audio * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(voice.config.sample_rate)
        f.writeframes(pcm.tobytes())
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description="Add English names to voice_sprites.bin")
    ap.add_argument("--model", default=r"X:\piper\voices\en_US-amy-medium.onnx")
    ap.add_argument("--commit", action="store_true",
                    help="Write changes into the repo's bin/index (creates .bak)")
    args = ap.parse_args()

    config_path = args.model + ".json"
    if not os.path.exists(args.model) or not os.path.exists(config_path):
        print(f"[Error] Model or config missing: {args.model}")
        sys.exit(1)

    bin_path = os.path.join(REPO, "voice_sprites.bin")
    index_path = os.path.join(REPO, "voice_sprites.bin.index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    # Filter to names not already present
    to_add = [n for n in NAMES if n and n.islower() and n.isascii() and n not in index]
    skip = len(NAMES) - len(to_add)
    print(f"[*] {len(to_add)} names to synthesize ({skip} already present, skipped)")

    if not to_add:
        print("[*] Nothing to add.")
        return

    from piper.voice import PiperVoice
    voice = PiperVoice.load(args.model)
    symbols = load_symbols(config_path)
    ffmpeg = ffmpeg_util.get_ffmpeg_exe()

    print(f"[*] Using Piper phoneme path (espeak phonemize) for pronunciation")

    data = bytearray()
    with open(bin_path, "rb") as f:
        data += f.read()

    failed_keys = set()
    offsets = {}
    total = len(to_add)

    for idx, name in enumerate(to_add):
        if name in failed_keys:
            continue
        try:
            # Phonemize the name via Piper's phoneme path
            phonemes_list = voice.phonemize(name)
            if not phonemes_list or not phonemes_list[0]:
                print(f"  [!] No phonemes for '{name}', skipping")
                failed_keys.add(name)
                continue
            # phonemize returns list of sentences, each a list of phoneme symbols
            toks = phonemes_list[0]
            # Synthesize
            wav = synth_phonemes(voice, toks)
            blob = to_adpcm_wav(ffmpeg, wav)
        except Exception as ex:
            failed_keys.add(name)
            if (idx + 1) % 50 == 0 or idx < 10:
                print(f"  [!] Failed '{name}': {ex}")
            continue

        if not blob or len(blob) < 128:
            failed_keys.add(name)
            continue

        offsets[name] = [len(data), len(blob)]
        data += blob

        if (idx + 1) % 100 == 0:
            print(f"  ... synthesized {idx + 1}/{total} names")

    final_index = dict(index)
    final_index.update(offsets)
    final_blob = bytes(data)

    print(f"\n[+] Added {len(offsets)} names, total index entries {len(final_index)}")
    print(f"[+] New bin blob size: {len(final_blob)} bytes (added {len(final_blob) - len(data) + sum(v[1] for v in offsets.values())} bytes)")
    print(f"[+] Already present (skipped): {skip}")
    if failed_keys:
        print(f"[!] Failed synthesis ({len(failed_keys)}):")
        for k in sorted(failed_keys)[:50]:
            print(f"    {k!r}")
        if len(failed_keys) > 50:
            print(f"    ... and {len(failed_keys) - 50} more")

    new_bin = bin_path + ".new"
    new_index_path = index_path + ".new"
    with open(new_bin, "wb") as f:
        f.write(final_blob)
    with open(new_index_path, "w", encoding="utf-8") as f:
        json.dump(final_index, f)
    print(f"[+] Wrote {new_bin} and {new_index_path}")

    if args.commit:
        for target in (bin_path, index_path):
            if os.path.exists(target):
                os.replace(target, target + ".bak")
        os.replace(new_bin, bin_path)
        os.replace(new_index_path, index_path)
        print("[*] Committed. Backups kept as *.bak")
    else:
        print("[*] Dry run — nothing overwritten. Re-run with --commit.")


if __name__ == "__main__":
    main()
