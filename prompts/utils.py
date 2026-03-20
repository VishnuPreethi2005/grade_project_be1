from django.conf import settings
import json

import razorpay


class RazorpayOrder:
    key = settings.RAZORPAY_KEY
    secret = settings.RAZORPAY_KEY_SECRET

    def create_order(self, amount):

        client = razorpay.Client(auth=(self.key, self.secret))

        amount_in_paisa = int(amount) * 100

        DATA = {
            "amount": amount_in_paisa,
            "currency": "INR",
            "receipt": "receipt#1",
        }

        order = client.order.create(data=DATA)

        return json.loads(json.dumps(order))
