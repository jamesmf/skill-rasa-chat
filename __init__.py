# The MIT License (MIT)
# Copyright (c) 2019 jamesmf

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft.util.log import LOG
from mycroft.util.parse import match_one
import requests


class ButtonValidator:
    def __init__(self, values, threshold):
        self.values = values
        self.threshold = threshold

    def validate(self, utterance):
        best = match_one(utterance, self.values)
        return best[1] > self.threshold


class RasaSkill(MycroftSkill):
    button_match_threshold = 0.6
    button_attempts_max = 3

    # The constructor of the skill, which calls MycroftSkill's constructor
    def __init__(self):
        super(RasaSkill, self).__init__(name="RasaSkill")
        self.conversation_active = False
        self.rasa_host = "http://localhost:5005/"
        self.append_endpoint = (
            self.rasa_host + "conversations/mycroft_user/messages?include_events=NONE"
        )
        self.predict_endpoint = self.rasa_host + "conversations/mycroft_user/predict"
        self.action_endpoint = (
            self.rasa_host + "conversations/mycroft_user/execute?include_events=APPLIED"
        )

    @intent_handler(IntentBuilder("").require("Chatwithrasa"))
    def handle_talk_to_rasa_intent(self, message):
        response = self.get_response("connecting.to.rasa")
        self.conversation_active = True
        while response is not None and self.conversation_active:
            messages = self.get_rasa_response(response)
            if len(messages) > 1:
                for rasa_message in messages[:-1]:
                    self.speak(rasa_message)
            if len(messages) == 0:
                messages = ["no response from rasa"]
            response = self.handle_final_output(messages[-1])

        self.speak("disconnecting from rasa")

    def handle_final_output(self, message, attempts=0):
        if attempts > self.button_attempts_max:
            return None
        if attempts > 0:
            self.speak("You can also say Option 1, Option 2, etc")
        # if we have buttons, handle them
        if "buttons" in message:
            # speak the text on the message
            self.speak(message["text"])

            buttons = message["buttons"]
            button_titles = [b["title"] for b in buttons]

            if len(buttons) == 1:
                # if we have a single button, assume it's a confirmation
                self.speak("To confirm, say")
            elif len(buttons) > 1:
                # if we have many buttons, list the options
                self.speak("You can say")
            # read out our button title options, separated by "Or"
            for button in buttons[:-1]:
                self.speak(button["title"])
                self.speak("Or")
            # read the final button option, and await a response
            # that is in the list of what we just returned OR
            # is "option 1", "option 2", ..., "option N"  N
            option_list = [f"option {i+1}" for i in range(len(buttons))]
            validation_options = button_titles + option_list
            button_validator = ButtonValidator(
                validation_options, self.button_match_threshold
            )
            print(f"trying attempt {attempts}")
            response = self.get_response(
                button_titles[-1],
                validator=button_validator.validate,
                num_retries=0,
                on_fail=self.on_failed_button,
            )
            print(f"response {response}")
            # if response is not None, we passed the validator
            if response is not None:
                best_match = match_one(response, validation_options)
                response = best_match[0]
                best_ind = validation_options.index(response)
                if best_ind >= len(buttons):
                    best_ind = best_ind % len(buttons)
                response = buttons[best_ind]["payload"]
                return response
            return self.handle_final_output(message, attempts=attempts + 1)
        # if we don't have buttons, just get_response
        return self.get_response(message["text"], num_retries=0)

    def on_failed_button(self, utt):
        return "Sorry I didn't catch that."

    def get_rasa_response(self, utterance):
        if "stop" in utterance.lower():
            self.conversation_active = False
            return [{"text": "goodbye from rasa"}]
        messages = self.hit_rasa(utterance)
        print(messages)
        return messages

    def stop(self):
        self.conversation_active = False

    def hit_rasa(self, utterance):
        # send our utterance to rasa
        print(f"sending {utterance} to {self.append_endpoint}")
        append_response = requests.post(
            self.append_endpoint, json={"text": utterance, "sender": "user"}
        )
        # run actions until we get an action_listen response
        action = None
        outputs = []
        while action != "action_listen":
            response = requests.post(self.predict_endpoint).json()
            # send the most likely action to the execute endpoint
            action = response["scores"][0]["action"]
            self.log.debug(action)
            print(f"sending {action} to {self.action_endpoint}")
            run_action = requests.post(
                self.action_endpoint, json={"name": action}
            ).json()
            outputs += [m for m in run_action["messages"]]
        self.log.debug(outputs)
        return outputs


def create_skill():
    return RasaSkill()
