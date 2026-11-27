package com.mochyy.mochymusic.guardian

import android.content.Context
import android.content.Intent
import android.util.Base64
import com.clerk.api.Clerk
import com.mochyy.mochymusic.MainActivity
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.security.KeyFactory
import java.security.spec.X509EncodedKeySpec

/** Explicitly gated staging runtime. No V1 fallback. A process restart requires
 * an online authenticated lease refresh; device reboot also invalidates time.
 */
internal object GuardianV2Runtime {
    private data class Binding(val subject:String,val session:String,val account:String)
    @Volatile private var binding: Binding? = null
    private val mutex = Mutex()
    private val stateLock = Any()
    private var generation = 0L
    private val flags = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    private const val origin = "https://void-guardian-v2-stage.onrender.com"
    private const val publicKey = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEQd2EkFTXZBKBZW0S2HRm2kVFUFUjS9KmxUHDa1c8RktpEJ-gcHU33Z5UmiXk5p2pVi-R1tZI4NpuEGBOV3z8Cw"
    private fun decode(s:String,max:Int):ByteArray {
        require(s.length in 1..max && Regex("[A-Za-z0-9_-]+").matches(s))
        return Base64.decode(s,flags).also { require(Base64.encodeToString(it,flags)==s) }
    }
    private fun cache(context:Context)=GuardianLeaseCache(context,KeyFactory.getInstance("EC")
        .generatePublic(X509EncodedKeySpec(decode(publicKey,256))),"gate")
    private fun current(b:Binding)=Clerk.isInitialized.value &&
        Clerk.userFlow.value?.id==b.subject && Clerk.session?.id==b.session

    fun allowed(context:Context):Boolean = synchronized(stateLock) {
        val b=binding ?: return@synchronized false
        runCatching { current(b) && GuardianLocalLibraryOwner.status(context, b.account) == LocalLibraryBinding.Status.MATCH && cache(context).active(b.account) }.getOrDefault(false)
    }

    private fun revokeLocked(context: Context) {
        generation++
        binding = null
        runCatching { cache(context).clear() }
    }

    fun clear(context: Context) {
        synchronized(stateLock) { revokeLocked(context) }
        GuardianAutomaticSync.disable()
        GuardianGate.changed()
    }

    /** Recheck under the same lock as lease publication so a stale observer
     * cannot revoke a freshly authorized session. Never hold stateLock while
     * cancelling sync, whose session predicate also acquires stateLock. */
    fun clearIfLocked(context: Context): Boolean {
        synchronized(stateLock) {
            if (allowed(context)) return false
            revokeLocked(context)
        }
        GuardianAutomaticSync.disable()
        GuardianGate.changed()
        return true
    }

    suspend fun authorize(context:Context,client:GuardianAccountClient,account:String,confirmLocalLibrary:Boolean = false):Boolean =
        mutex.withLock {
            withContext(Dispatchers.IO) {
                try {
                    val initial=ClerkQaBridge.currentSession()
                    val b=Binding(initial.subject,initial.sessionId,account)
                    val startGeneration=synchronized(stateLock){generation}
                    require(Regex("[a-f0-9]{32}").matches(account))
                    if (!LocalLibraryBinding.canUse(GuardianLocalLibraryOwner.status(context, account), confirmLocalLibrary)) return@withContext false
                    val status=client.request("status",emptyMap())
                    if(status.getString("account")!=account || status.getString("status")!="active"){
                        clear(context);return@withContext false
                    }
                    val lease=cache(context)
                    val anchor=lease.anchor()
                    val reply=client.request("lease",emptyMap())
                    val payload=decode(reply.getString("payload"),4096)
                    val sig=decode(reply.getString("signature"),128)
                    val epoch=JSONObject(String(payload,Charsets.US_ASCII)).getLong("issued_at")
                    val saved=synchronized(stateLock) {
                        if(generation!=startGeneration || !current(b)) return@synchronized false
                        if(!lease.saveFresh(payload,sig,account,epoch,anchor)) return@synchronized false
                        if (!lease.active(account) || !GuardianLocalLibraryOwner.claim(context, account, confirmLocalLibrary)) {
                            lease.clear(); return@synchronized false
                        }
                        binding=b
                        true
                    }
                    if(saved) GuardianGate.changed()
                    saved
                } catch(e:CancellationException){throw e}
                catch(e:GuardianAccountClient.RequestFailed){
                    if(e.status==401 || e.status==403) clear(context)
                    false
                } catch(_:Exception){false}
            }
        }

    suspend fun refresh(context:Context):Boolean {
        val b=binding ?: return false
        if(!current(b)){clear(context);return false}
        val client=GuardianAccountClient(origin,{ClerkQaBridge.currentSession()},b.subject,b.session)
        val refreshed = authorize(context,client,b.account)
        if (refreshed && allowed(context)) GuardianAutomaticSync.schedule(b.account)
        else clearIfLocked(context)
        return refreshed
    }

    suspend fun enableAutomaticSync(context: Context, account: String): Boolean = withContext(Dispatchers.IO) {
        val app = context.applicationContext
        val b = binding ?: return@withContext false
        if (b.account != account || !allowed(app)) return@withContext false
        val active = { binding == b && current(b) && allowed(app) }
        val client = GuardianAccountClient(origin, { ClerkQaBridge.currentSession() }, b.subject, b.session)
        val cloud = GuardianQaCloud(app, (app as com.mochyy.mochymusic.App).musicDatabase, client,
            ownsLibrary = { id -> GuardianLocalLibraryOwner.status(app, id) == LocalLibraryBinding.Status.MATCH },
            isCurrent = active)
        GuardianAutomaticSync.enable(account, cloud, active)
    }

    fun openMusic(context:Context) {
        if(!allowed(context)) return
        context.startActivity(Intent(context,MainActivity::class.java).apply {
            action=Intent.ACTION_MAIN
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        })
        (context as? android.app.Activity)?.finish()
    }
}
