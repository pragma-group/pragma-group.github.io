#include <iostream>
using std::cout;
using std::endl;

// some domain objects
class Dog {
public:
    void talk() const { cout << "woof woof" << endl; }
};

class CuckooClock {
public:
    void talk() const { cout << "cuckoo cuckoo" << endl; }
    void talk_in_German() const { cout << "wachet auf!" << endl; }
};

class BigBenClock {
public:
    void talk() const { cout << "take a tea-break"   << endl; }
    void playBongs() const { cout << "bing bong bing bong" << endl; }
};

class SilentClock {
    // doesn't talk
};

// generic template to provide non-inheritance-based
// polymorphism
template <class T>
class Talkative {
    T& t;
public:
    Talkative(T& obj) : t(obj) {  }
    void talk() const { t.talk(); }
    void talk_in_German() const { t.talk_in_German(); }
};

// specialization to adapt functionality
template <>
class Talkative<BigBenClock> {
    BigBenClock& t;
public:
    Talkative(BigBenClock& obj)
    : t(obj)    {}
    void talk() const { t.playBongs(); }
};

// specialization to add missing functionality
template <>
class Talkative<SilentClock> {
    SilentClock& t;
public:
    Talkative(SilentClock& obj)
    : t(obj)    {}
    void talk() const { cout << "tick tock" << endl; }
};

// adapter function to simplify syntax in usage
template <class T>
Talkative<T> makeTalkative(T& obj) {
    return Talkative<T>(obj);
}

// function to use an object which implements the
// Talkative template-interface
template <class T>
void makeItTalk(Talkative<T> t)
{
    t.talk();
}

int main()
{
    Dog         aDog;
    CuckooClock aCuckooClock;
    BigBenClock aBigBenClock;
    SilentClock aSilentClock;

    // use objects in contexts which do not require talking
    // ...
    Talkative<Dog> td(aDog);
    td.talk();                                    // woof woof

    Talkative<CuckooClock> tcc(aCuckooClock);
    tcc.talk();                               // cuckoo cuckoo

    makeTalkative(aDog).talk();                   // woof woof
    makeTalkative(aCuckooClock).talk_in_German();    // wachet
                                                     //   auf!

    makeItTalk(makeTalkative(aBigBenClock));      // bing bong
                                                  // bing bong
    makeItTalk(makeTalkative(aSilentClock));      // tick tock

    return 0;
}


