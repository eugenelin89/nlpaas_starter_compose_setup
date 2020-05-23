# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/core/actions/#custom-actions/


# This is a simple example for a custom action which utters "Hello World!"

from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import rasa.utils

# SqlAlchemy
from sqlalchemy import Column, ForeignKey, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy.exc
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import psycopg2

from rasa.core.utils import AvailableEndpoints
import requests
import json
import logging
import random
import time
import datetime
logger = logging.getLogger(__name__)
_endpoints = AvailableEndpoints.read_endpoints("endpoints.yml")
_credentials = rasa.utils.io.read_config_file("credentials.yml")

# To get FB User Profile, use something like:
# See: https://developers.facebook.com/tools/explorer
# and https://developers.facebook.com/docs/graph-api/explorer/


Base = declarative_base()

class Human(Base):
    __tablename__ = 'human'
    id = Column(Integer, primary_key=True)
    fb_id = Column(String(250))
    first_name = Column(String(250))
    last_name = Column(String(250))
    create_time = Column(DateTime)

class Challenge(Base):
    __tablename__ = 'challenge'
    id = Column(Integer, primary_key=True)
    score = Column(Integer)
    time = Column(Float) # time to complete challenge, in seconds
    create_time = Column(DateTime)
    human_id = Column(Integer, ForeignKey("human.id"))
    human = relationship(Human)

class ActionReset(Action):

    def name(self) -> Text:
        return "action_reset"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info("\n\naction_reset\n\n")

        return [SlotSet("a_b_ans", ""), SlotSet("q_num", "0"), SlotSet("score", "0"), SlotSet("start_time", "0")]



class ActionMultiplicationTableChallenge(Action):
    def name(self) -> Text:
        return "action_multiplication_table_challenge"
    def __init__(self):
        # Set up datastore connection.
        from sqlalchemy.engine.url import URL
        
        logger.info(_endpoints.tracker_store.kwargs)
        dialect = _endpoints.tracker_store.kwargs["dialect"] #"postgresql"
        username = _endpoints.tracker_store.kwargs["username"] #"postgres"
        password = _endpoints.tracker_store.kwargs["password"]
        login_db = _endpoints.tracker_store.kwargs["login_db"] #"postgres"
        host = _endpoints.tracker_store.url
        port = None
        db = _endpoints.tracker_store.kwargs["db"] #"rasa"
        query = None
        
	    #login_db: Alternative database name to which initially connect, and create
        # the database specified by `db` (PostgreSQL only).
        engine_url = URL(dialect, username, password, host, port, login_db, query)
        # if `login_db` has been provided, use currentpassword channel with
        # that database to create working database `db`
        try:
            self.engine = create_engine(engine_url)	
	        # Create Database
            self._create_database(self.engine, db)
            engine_url.database = db
            self.engine = create_engine(engine_url)
            Base.metadata.create_all(self.engine)
        except (
            sqlalchemy.exc.OperationalError,
            sqlalchemy.exc.ProgrammingError,
            psycopg2.OperationalError
        ) as e:
            # Several Rasa services started in parallel may attempt to
            # create tables at the same time. That is okay so long as
            # the first services finishes the table creation.
            logger.error(f"Could not create tables: {e}")
        self.sessionmaker = sessionmaker(bind=self.engine)

    @staticmethod
    def _create_database(engine: "Engine", db: Text):
        """Create database `db` on `engine` if it does not exist."""
        conn = engine.connect()
        cursor = conn.connection.cursor()
        cursor.execute("COMMIT")
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db}'")
        exists = cursor.fetchone()
        if not exists:
            try:
                cursor.execute(f"CREATE DATABASE {db}")
            except psycopg2.IntegrityError as e:
                logger.error(f"Could not create database '{db}': {e}")
        cursor.close()
        conn.close()

    def save_result(self, fb_id, score, time):
        logger.info("save_result called")
        """ Save score to the postgresql db using sqlalchemy """
        # Check to see if human already in db. if not, add to human table.
        sess = self.sessionmaker()
        human = sess.query(Human).filter(Human.fb_id == fb_id).one_or_none()

        if human is None:
            # need to get the first_name and last_name of the human
            # From credential file, get the token.
            token = _credentials["facebook"]["page-access-token"]
            url = "https://graph.facebook.com/{0}?fields=first_name,last_name&access_token={1}".format(fb_id, token)
            profile = requests.get(url).json()
            human = Human(fb_id = fb_id, first_name = profile.get("first_name","Foo"), last_name = profile.get("last_name","Bar"), create_time = datetime.datetime.now())
            sess.add(human)
            sess.commit()
        logger.info("human ID: "+ str(human.id))
        # Insert challenge
        challenge = Challenge(score =  int(score), time = float(time), create_time = datetime.datetime.now(), human = human )
        sess.add(challenge)
        sess.commit()
    
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info("\n\n")
        logger.info("*******************************************")
        logger.info("Enter action_multiplication_table_challenge")

        event_length = len(tracker.current_state()['events'])
        #logger.debug(json.dumps(tracker.current_state(),sort_keys=True, indent=4))
        #logger.info(json.dumps(tracker.current_state(),sort_keys=True, indent=4))
        logger.info("Number of events:"+str(event_length))
        # Check to see if we are waiting for an answer
        # If we expect an answer, check text is correct answer
        # Check to see if we need to provide the next question
        # If next question needed, send the next question
        # If we are at the end of questions and answers, provide result.
        # - Score
        # - Time
        # - Link to leaderboard.
        
        #my_text = tracker.current_state()["latest_input_channel"] + ": "+ tracker.current_state()["sender_id"]
        #i = 1 # index of question, should be 1 to 20. 
        last_q = 20
        ans_utterance = tracker.current_state()["latest_message"]["text"]
        score = tracker.get_slot("score")
        q_num = tracker.get_slot("q_num")
        qna = tracker.get_slot("a_b_ans")
        intent = tracker.current_state()["latest_message"]["intent"]["name"]
        
        start_time = tracker.get_slot("start_time")
        cur_time = str(time.time()) # for consistency, lets make all var str
        if start_time == "0":
            start_time = cur_time

        time_delta = str(datetime.timedelta(seconds= float(cur_time) - float(start_time)))

        logger.info("Time since start: "+ time_delta)
        logger.info("Utterance: " + ans_utterance)   
        logger.info("score: "+ score)
        logger.info("q_num: "+ q_num)
        logger.info("qna: " + qna)
        logger.info("intent: " + intent)
        logger.info("start_time: " + start_time)
        logger.info("cur_time: " + cur_time)

        response = ""


        if intent == "answer": 
            # Received an answer from user
            ans_utterance = tracker.current_state()["latest_message"]["entities"][0]["value"]
            # check the answer
            logger.info("Question (" + q_num + "): Previous QA: " + qna)
            try:
                if int(qna.split(",")[2]) == int(ans_utterance):
                    response = response + "Correct!\n"
                    #dispatcher.utter_message(text= "Correct!")
                    score = str(int(score) + 1)
                else:
                    response = response + "Wrong..."
                    #dispatcher.utter_message(text= "Wrong...")
            except:
                pass
            logger.info("Score: " + score)

        # User ansered the last question
        challenge_completed = False
        if int(q_num) == last_q and intent == "answer":
            logger.info("End of challenge")
            # tabulate and utter back the result
            time_str = ""
            rest_part = time_delta
            time_parts = time_delta.split(",")
            if len(time_parts) > 1:
                day_part = time_parts[0]
                rest_part = time_parts[1]
                time_str += day_part + " "
            time_lst = rest_part.split(":")
            hr = time_lst[0]
            m = time_lst[1]
            s = time_lst[2]
            if int(hr) > 0:
                if int(hr) > 1:
                    time_str += hr + " hours "
                else:
                    time_str += hr + " hour "
            if int(m) > 0 or int(hr) > 0:
                if int(m) > 1:
                    time_str += m + " minutes "
                else:
                    time_str += m + " minute "
            time_str += s + " seconds"

            response = response + "Challenge Acomplished!\n" + "Your score is " + score + " out of " + str(last_q) + ".\n Your time is: " + time_str

            #dispatcher.utter_message(text = "Challenge Accomplished!")
            #dispatcher.utter_message(text = "Your score: " + score + " out of " + str(last_q))
            #dispatcher.utter_message("Your time: " + time_str)

            # Save the result of the challenge
            fb_id = tracker.current_state().get("sender_id", "foobar")
            # I am the default user
            if fb_id == "default":
                logger.info("Default FB User. Use mine.")
                fb_id = _credentials["facebook"].get("default_fb_id","foobar")
            logger.info("facebok ID: "+fb_id)
            self.save_result(fb_id,score, float(cur_time) - float(start_time))
            # reset slots
            qna = ""
            q_num = "0"
            score = "0" 
            start_time = "0"
            challenge_completed = True

        
        # if in the middle of a challenge and the intent is not "answer"
        # that is, if q_num != 0 and intent != answer
        # We should repeat the question.
        # We should not generate new question or increment q_num
        if challenge_completed == False and int(q_num) != 0 and intent != "answer":
            logger.info("In the middle of challenge, user uttered something unrelated")
            # Utter original
            orig = qna.split(",")
            a = int(orig[0])
            b = int(orig[1])
            q = q = "Question ("+ str(q_num) + ") What is " + str(a) + " X " + str(b) + " = ?"
            ans = a * b
            qna = ','.join([str(a), str(b), str(ans)])
            response = response + q
            #dispatcher.utter_message(text= q)

        if challenge_completed == False and int(q_num) == 0: # we are starting challenge. 
            logger.info("Start Challenge!")
            #start_time = str(float(cur_time) - 3600) # FOR TESTING!

        if challenge_completed == False and (int(q_num) == 0 or intent == "answer"):
            logger.info("First question or user provided an answer")
            # generate next question and increment q_num
            q_num = str(int(q_num) + 1)
            # Generate 2 random integers between 0 and 9
            a = random.randint(0,9)
            b = random.randint(0,9)
            q = "Question ("+ str(q_num) + ") What is  " + str(a) + " X " + str(b) + " = ?"
            ans = a * b
            qna = ','.join([str(a), str(b), str(ans)])
            response = response + q
            #dispatcher.utter_message(text= q)

        dispatcher.utter_message(text = response)
        logger.info("Exit action_multiplication_table_challenge")
        logger.info("*******************************************")
        return [SlotSet("a_b_ans", qna), SlotSet("q_num", q_num), SlotSet("score", score), SlotSet("start_time", start_time)]

class ActionHelloDeepChat(Action):

    def name(self) -> Text:
        return "action_hello_deepchat"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        logger.info("\n\naction_hello_deepchat")
        event_length = len(tracker.current_state()['events'])
        logger.info("Number of events:"+str(event_length))
                
        my_text = tracker.current_state()["latest_input_channel"] + ": "+ tracker.current_state()["sender_id"]
        dispatcher.utter_message(text= my_text)

        logger.info("exit action_hello_deepchat")
        return []
