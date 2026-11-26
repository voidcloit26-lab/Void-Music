package com.mochyy.mochymusic.guardian
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec
fun main() {
    val key = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
    val a = "a".repeat(32); val d = "b".repeat(64); val h = "c".repeat(64); val s = "d".repeat(64)
    fun signed(text: String): Pair<ByteArray,ByteArray> { val b=text.toByteArray(); return b to Signature.getInstance("SHA256withECDSA").apply { initSign(key.private); update(b) }.sign() }
    fun reject(f: () -> Unit) { check(runCatching(f).isFailure) }
    val (l, ls) = signed("""{"account":"$a","audience":"online.voidbot.music","device":"$d","expires_at":1800000060,"issued_at":1800000000,"membership_expires_at":null,"version":2}""")
    val now=1800000000L
    check(SignedGuardianPolicy.lease(l,ls,key.public,a,d,now,now).expiresAt == now+60)
    reject { SignedGuardianPolicy.lease(l,ls,key.public,a,d,now+60,now) }
    reject { SignedGuardianPolicy.lease(l,ls,key.public,a,d,now-1,now) }
    reject { SignedGuardianPolicy.lease(l,ls,key.public,a,h,now,now) }
    reject { SignedGuardianPolicy.lease(l,ByteArray(64),key.public,a,d,now,now) }
    fun manifest(seq: Long, min: Long = 74) = signed("""{"apk_bytes":1234,"apk_sha256":"$h","channel":"stable","expires_at":1800000060,"issued_at":1800000000,"latest":75,"minimum":$min,"package":"online.voidbot.music","sequence":$seq,"signer_sha256":"$s","version_name":"1.0.0"}""")
    val (r,rs)=manifest(2); val release=SignedGuardianPolicy.release(r,rs,key.public,now)
    check(release.sequence==2L && release.decision(73)=="required" && release.decision(74)=="available" && release.decision(75)=="current")
    val (old,os)=manifest(1); reject { SignedGuardianPolicy.release(old,os,key.public,now,release) }
    val (changed,cs)=manifest(2,75); reject { SignedGuardianPolicy.release(changed,cs,key.public,now,release) }
    reject { SignedGuardianPolicy.release(r,rs,key.public,now+60) }
    check(SignedGuardianPolicy.release(r,rs,key.public,now,release)==release)
    println("PASS: 10 signed policy smoke checks")
}
