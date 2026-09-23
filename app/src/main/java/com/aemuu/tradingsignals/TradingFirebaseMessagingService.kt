package com.aemuu.tradingsignals

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class TradingFirebaseMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)

        Log.d("FCM_RECEIVER", "High-Priority FCM Message Received in Sub-Second!")

        val data = remoteMessage.data
        val symbol = data["symbol"] ?: "UNKNOWN"
        val action = data["action"] ?: "SIGNAL"
        val price = data["price"] ?: "0.00"
        val timestamp = data["timestamp"] ?: ""

        val title = "🚨 $action SIGNAL: $symbol"
        val body = "Entry: $price | Time: $timestamp UTC"

        ExactAlarmHelper.triggerInstantSignalAlert(applicationContext, title, body)
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d("FCM_TOKEN", "New FCM Token Generated: $token")
    }
}